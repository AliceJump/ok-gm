import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from src.dmm.browser_proxy import ProxySettings, dmm_bypass_removed, restore_browser_proxy, temporary_browser_proxy
from src.dmm.session import DEFAULT_PROXY, DmmError


class MemoryProxy:
    def __init__(self, value):
        self.value = value
        self.writes = []

    def get(self):
        return self.value

    def set(self, value):
        self.value = value
        self.writes.append(value)


class TemporaryProxyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.original = ProxySettings(3, '127.0.0.1:10808', '<local>;localhost;127.*;10.*;dmm.com;*.dmm.com;*.dmm.co.jp')
        self.backend = MemoryProxy(self.original)
        self.journal = self.root / 'temporary-browser-proxy.json'

    def test_removes_dmm_bypass_and_preserves_local_rules(self):
        self.assertEqual(dmm_bypass_removed(self.original.bypass), '<local>;localhost;127.*;10.*')
        self.assertEqual(dmm_bypass_removed('*.DMM.COM;*.co.jp;192.168.*;example.com'), '192.168.*;example.com')

    def test_restore_after_success(self):
        with temporary_browser_proxy(DEFAULT_PROXY, self.root, self.backend):
            self.assertTrue(self.journal.exists())
            self.assertEqual(self.backend.value.bypass, '<local>;localhost;127.*;10.*')
        self.assertEqual(self.backend.value, self.original)
        self.assertFalse(self.journal.exists())

    def test_restore_after_cancel_or_timeout(self):
        for error in (KeyboardInterrupt, DmmError):
            with self.subTest(error=error), self.assertRaises(error):
                with temporary_browser_proxy(DEFAULT_PROXY, self.root, self.backend):
                    raise error()
            self.assertEqual(self.backend.value, self.original)
            self.assertFalse(self.journal.exists())

    def test_restore_explicit_server_and_auto_proxy_flags(self):
        original = ProxySettings(9, '', '<local>;*.dmm.com')
        self.backend.value = original
        with temporary_browser_proxy('http://127.0.0.1:10809', self.root, self.backend):
            self.assertEqual(self.backend.value, ProxySettings(3, '127.0.0.1:10809', '<local>'))
        self.assertEqual(self.backend.value, original)

    def test_preserves_external_proxy_change_as_a_unit(self):
        external = ProxySettings(3, '127.0.0.1:9999', 'localhost;example.com')
        with temporary_browser_proxy(DEFAULT_PROXY, self.root, self.backend):
            self.backend.value = external
        self.assertEqual(self.backend.value, external)
        self.assertFalse(self.journal.exists())

    def test_recovers_saved_state_after_process_termination(self):
        applied = ProxySettings(3, self.original.server, '<local>;localhost;127.*;10.*')
        self.journal.write_text(json.dumps({'original': asdict(self.original), 'applied': asdict(applied)}))
        self.backend.value = applied
        self.assertTrue(restore_browser_proxy(self.root, self.backend))
        self.assertEqual(self.backend.value, self.original)
        self.assertFalse(restore_browser_proxy(self.root, self.backend))

    def test_restore_failure_retains_recovery_journal(self):
        applied = ProxySettings(3, self.original.server, '<local>;localhost;127.*;10.*')
        self.journal.write_text(json.dumps({'original': asdict(self.original), 'applied': asdict(applied)}))
        self.backend.value = applied
        self.backend.set = lambda value: (_ for _ in ()).throw(OSError('simulated failure'))
        with self.assertRaises(DmmError):
            restore_browser_proxy(self.root, self.backend)
        self.assertTrue(self.journal.exists())


if __name__ == '__main__':
    unittest.main()
