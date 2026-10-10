import base64
import json
import tempfile
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.config import DMM_PROXY_KEY
from src.dmm.session import DmmError
from src.dmm.xray import NODE_ENABLED_KEY, NodeStore, NodePool, PoolAdapter, operation_proxy, parse_node, runtime_config
import requests
import win32crypt


LINK = 'vless://00000000-0000-0000-0000-000000000001@node.example:443?security=reality&sni=example.com&pbk=public&sid=abcd&flow=xtls-rprx-vision#Japan'


class NodeTests(unittest.TestCase):
    def test_supported_links_preserve_node_and_transport(self):
        node = parse_node(LINK)
        self.assertEqual(node['name'], 'Japan')
        stream = node['outbound']['streamSettings']
        self.assertEqual(stream['realitySettings']['shortId'], 'abcd')
        self.assertEqual(node['outbound']['settings']['vnext'][0]['address'], 'node.example')
        vmess = {'add': 'node.example', 'port': 443, 'id': 'uuid', 'net': 'ws', 'tls': 'tls', 'path': '/ws', 'host': 'host.example'}
        link = 'vmess://' + base64.b64encode(json.dumps(vmess).encode()).decode()
        self.assertEqual(parse_node(link)['outbound']['streamSettings']['wsSettings']['path'], '/ws')
        credential = base64.b64encode(b'aes-128-gcm:secret-value').decode()
        ss = parse_node(f'ss://{credential}@node.example:443#SS')
        self.assertEqual(ss['outbound']['settings']['servers'][0]['password'], 'secret-value')
        trojan = parse_node('trojan://secret-value@node.example:443#JP')
        self.assertEqual(trojan['outbound']['streamSettings']['security'], 'tls')

    def test_full_config_discards_routes_listeners_logs_and_direct_fallback(self):
        node = parse_node(LINK)
        raw = {'outbounds': [node['outbound'], {'protocol': 'freedom'}],
               'inbounds': [{'listen': '0.0.0.0', 'port': 80}], 'log': {'access': 'secret.log'},
               'routing': {'rules': [{'outboundTag': 'direct'}]}}
        config = runtime_config(parse_node(json.dumps(raw)), 12345)
        self.assertEqual(len(config['outbounds']), 1)
        self.assertEqual(config['inbounds'][0]['listen'], '127.0.0.1')
        self.assertEqual(config['log'], {'loglevel': 'none'})
        self.assertNotIn('routing', config)
        raw['outbounds'].append(node['outbound'])
        with self.assertRaises(DmmError):
            parse_node(json.dumps(raw))

    def test_unsafe_dependencies_are_rejected_without_leaking_secrets(self):
        raw = parse_node(LINK)['outbound']
        raw['proxySettings'] = {'tag': 'another-node'}
        with self.assertRaises(DmmError):
            parse_node(json.dumps(raw))
        del raw['proxySettings']
        raw['streamSettings']['tlsSettings'] = {'certificates': [{'certificateFile': 'secret-value.pem'}]}
        with self.assertRaises(DmmError) as caught:
            parse_node(json.dumps(raw))
        self.assertNotIn('secret-value', str(caught.exception))
        with self.assertRaises(DmmError) as caught:
            parse_node('secret-value malformed config')
        self.assertNotIn('secret-value', str(caught.exception))

    def test_encrypted_storage_and_rejected_reimport_preserve_saved_node(self):
        with tempfile.TemporaryDirectory() as directory:
            store = NodeStore(Path(directory))
            store.save(parse_node(LINK))
            encrypted = store.path.read_bytes()
            self.assertNotIn(b'node.example', encrypted)
            self.assertEqual(store.load()['name'], 'Japan')
            with patch.object(store, 'install', return_value=Path('xray.exe')), \
                    patch('src.dmm.xray.subprocess.run', return_value=SimpleNamespace(returncode=1)), \
                    self.assertRaises(DmmError):
                store.import_node(LINK, 'http://127.0.0.1:10808')
            self.assertEqual(store.path.read_bytes(), encrypted)

    def core_mocks(self, stack, *, failed=False):
        process = Mock(pid=1234)
        process.poll.return_value = 1 if failed else None
        process.stdin.closed = False
        job = Mock()
        inlet = Mock()
        inlet.__enter__ = Mock(return_value=inlet)
        inlet.__exit__ = Mock(return_value=False)
        inlet.getsockname.return_value = ('127.0.0.1', 45678)
        for target, value in (
            ('NodeStore.ordered', [dict(parse_node(LINK), id='fixture', enabled=True)]), ('NodeStore.install', Path('xray.exe')),
            ('socket.socket', inlet), ('subprocess.Popen', process), ('win32job.CreateJobObject', job),
            ('win32job.QueryInformationJobObject', {'BasicLimitInformation': {'LimitFlags': 0}}),
            ('win32api.OpenProcess', Mock()),
            ('psutil.Process', SimpleNamespace(net_connections=lambda **kw: [SimpleNamespace(
                status='LISTEN', laddr=SimpleNamespace(ip='127.0.0.1', port=45678))]))):
            stack.enter_context(patch('src.dmm.xray.' + target, return_value=value))
        stack.enter_context(patch('src.dmm.xray.win32job.SetInformationJobObject'))
        stack.enter_context(patch('src.dmm.xray.win32job.AssignProcessToJobObject'))
        vpn = stack.enter_context(patch('src.dmm.launcher.start_vpn'))
        return process, job, vpn

    def test_isolated_proxy_uses_own_entry_and_closes_core_on_caller_error(self):
        with ExitStack() as stack:
            process, job, vpn = self.core_mocks(stack)
            with self.assertRaisesRegex(OSError, 'update-failed'):
                with operation_proxy({DMM_PROXY_KEY: 'http://127.0.0.1:10808', NODE_ENABLED_KEY: True}) as proxy:
                    self.assertEqual(proxy, 'http://127.0.0.1:45678')
                    raise OSError('update-failed')
            process.terminate.assert_called_once()
            job.Close.assert_called_once()
            vpn.assert_not_called()
            config = json.loads(process.stdin.write.call_args.args[0])
            self.assertEqual(len(config['outbounds']), 1)

    def test_failed_core_stops_without_external_proxy_fallback(self):
        with ExitStack() as stack:
            process, job, vpn = self.core_mocks(stack, failed=True)
            with self.assertRaises(DmmError):
                with operation_proxy({DMM_PROXY_KEY: 'http://127.0.0.1:10808', NODE_ENABLED_KEY: True}):
                    self.fail('failed core cannot yield a proxy')
            vpn.assert_not_called()
            job.Close.assert_called_once()

    def test_multiple_nodes_rotate_and_legacy_single_node_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            store = NodeStore(Path(directory))
            legacy = parse_node(LINK)
            store.path.write_bytes(win32crypt.CryptProtectData(json.dumps(legacy).encode(), 'fixture', None, None, None, 1))
            self.assertEqual(store.ordered()[0]['id'], 'legacy')
            store.save(parse_node(LINK.replace('node.example', 'other.example').replace('#Japan', '#Japan2')))
            nodes = store.ordered()
            self.assertEqual(len(nodes), 2)
            store.advance(nodes[0]['id'])
            self.assertEqual(store.ordered()[0]['name'], 'Japan2')
            store.change(nodes[1]['id'], 'toggle')
            self.assertEqual(len(store.ordered()), 1)
            store.change(nodes[0]['id'], 'remove')
            with self.assertRaises(DmmError):
                store.ordered()

    def test_connection_failure_tries_next_node_and_has_bounded_attempts(self):
        store = Mock()
        store.ordered.return_value = [dict(parse_node(LINK), id='a'), dict(parse_node(LINK), id='b')]
        transitions = []

        @contextmanager
        def process(node, *args):
            transitions.append('start-' + node['id'])
            try:
                yield 'proxy'
            finally:
                transitions.append('stop-' + node['id'])

        with patch('src.dmm.xray.node_process', process):
            pool = NodePool(store, Path('xray.exe'), 1234, lambda _: None, lambda: None)
            pool.failover()
            adapter = PoolAdapter(pool)
            request = requests.Request('GET', 'https://example.com').prepare()
            response = Mock(status_code=200)
            with patch.object(requests.adapters.HTTPAdapter, 'send', side_effect=[requests.ConnectionError(), response]) as send:
                self.assertIs(adapter.send(request), response)
                self.assertEqual(send.call_count, 2)
            self.assertEqual(transitions, ['start-a', 'stop-a', 'start-b'])
            store.advance.assert_called_once_with('b')
            with patch.object(requests.adapters.HTTPAdapter, 'send', side_effect=requests.ConnectionError()), self.assertRaises(DmmError):
                adapter.send(request)
            self.assertEqual(transitions[-1], 'stop-b')

    def test_http_auth_failure_does_not_trigger_node_switch(self):
        pool = Mock()
        adapter = PoolAdapter(pool)
        response = Mock(status_code=401)
        with patch.object(requests.adapters.HTTPAdapter, 'send', return_value=response):
            self.assertIs(adapter.send(requests.Request('GET', 'https://example.com').prepare()), response)
        pool.failover.assert_not_called()


if __name__ == '__main__':
    unittest.main()
