import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.dmm.accounts import AccountStore
from src.dmm.launcher import browser_login
from src.dmm.session import DmmError, DmmSession, atomic_write


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.store = AccountStore(self.root)
        stopped = patch('src.dmm.helper.ensure_game_stopped')
        self.stopped = stopped.start()
        self.addCleanup(stopped.stop)

    def fixture(self, root, token, viewer):
        session = DmmSession(root=root)
        session.auth = {'accessToken': token}
        session.http.cookies.set('session', token, domain='.dmm.com', path='/')
        session.accept_identity(viewer)
        return session

    def two_accounts(self):
        first = self.fixture(self.root, 'token-A', 'viewer-A')
        a = self.store.save_current('1', '账号一')
        second = self.fixture(self.root / 'fixture-B', 'token-B', 'viewer-B')
        b = self.store.save_current('2', '账号二', second.path, new=True)
        return a, b, first

    def test_switch_loads_complete_snapshot_and_refreshes_only_selected_slot(self):
        a, b, _ = self.two_accounts()
        previous_b = self.store.path(b['key']).read_bytes()
        self.store.switch('1')
        # The selected slot is authoritative, even if the active cache is stale.
        atomic_write(self.root / 'session.dpapi', previous_b)
        selected = DmmSession(root=self.root)
        self.assertEqual(selected.auth['accessToken'], 'token-A')
        self.assertEqual(selected.http.cookies.get('session'), 'token-A')
        selected.auth['accessToken'] = 'refreshed-A'
        selected.http.cookies.set('session', 'refreshed-A', domain='.dmm.com', path='/')
        selected.save()
        self.assertEqual(self.store.path(b['key']).read_bytes(), previous_b)
        self.assertEqual(DmmSession(root=self.root).auth['accessToken'], 'refreshed-A')
        self.store.switch('2')
        self.assertEqual(DmmSession(root=self.root).auth['accessToken'], 'token-B')
        self.assertNotIn(b'token-A', self.store.path(a['key']).read_bytes())

    def test_stale_session_cannot_overwrite_newly_selected_account(self):
        a, b, _ = self.two_accounts()
        stale = DmmSession(root=self.root)
        self.store.switch('1')
        old_a = self.store.path(a['key']).read_bytes()
        old_b = self.store.path(b['key']).read_bytes()
        stale.auth['accessToken'] = 'stale-write'
        with self.assertRaises(DmmError):
            stale.save()
        self.assertEqual(self.store.path(a['key']).read_bytes(), old_a)
        self.assertEqual(self.store.path(b['key']).read_bytes(), old_b)

    def test_running_game_prevents_switch_and_snapshot_before_writing(self):
        self.two_accounts()
        index = self.store.index.read_bytes()
        self.stopped.side_effect = DmmError('游戏正在运行')
        with self.assertRaises(DmmError):
            self.store.switch('1')
        with self.assertRaises(DmmError):
            self.store.save_current('3', '账号三')
        self.assertEqual(self.store.index.read_bytes(), index)

    def test_interrupted_snapshot_replacement_preserves_old_slot(self):
        a, _, _ = self.two_accounts()
        index = self.store.index.read_bytes()
        old = self.store.path(a['key']).read_bytes()

        def fail_index(path, value):
            if path == self.store.index:
                raise OSError('simulated write interruption')
            atomic_write(path, value)

        with patch('src.dmm.accounts.atomic_write', side_effect=fail_index), self.assertRaises(OSError):
            self.store.save_current('1', '替换名称')
        self.assertEqual(self.store.index.read_bytes(), index)
        self.assertEqual(self.store.path(a['key']).read_bytes(), old)

    def test_wrong_browser_account_never_replaces_selected_profile(self):
        self.fixture(self.root, 'token-A', 'viewer-A')
        a = self.store.save_current('1', '账号一')
        helper = SimpleNamespace(session=DmmSession(root=self.root))
        original = self.store.path(a['key']).read_bytes()

        def fake_login(target, progress, browser):
            target.session.auth = {'accessToken': 'token-B'}
            target.session.http.cookies.clear()
            target.session.http.cookies.set('session', 'token-B', domain='.dmm.com', path='/')
            target.session.save()

        def wrong_identity(session):
            session.accept_identity('viewer-B')

        with patch('src.dmm.launcher._browser_login', side_effect=fake_login), \
                patch.object(DmmSession, 'verify_game_identity', wrong_identity), self.assertRaises(DmmError):
            browser_login(helper)
        self.assertEqual(self.store.path(a['key']).read_bytes(), original)
        self.assertEqual(helper.session.auth['accessToken'], 'token-A')
        self.assertFalse(list((self.root / 'pending').glob('*/session.dpapi')))

    def test_same_account_browser_renewal_persists_cookie_and_token(self):
        self.fixture(self.root, 'token-A', 'viewer-A')
        self.store.save_current('1', '账号一')
        helper = SimpleNamespace(session=DmmSession(root=self.root))

        def fake_login(target, progress, browser):
            target.session.auth = {'accessToken': 'renewed-A'}
            target.session.http.cookies.set('session', 'renewed-A', domain='.dmm.com', path='/')
            target.session.save()

        with patch('src.dmm.launcher._browser_login', side_effect=fake_login), \
                patch.object(DmmSession, 'verify_game_identity', lambda session: session.accept_identity('viewer-A')):
            browser_login(helper)
        loaded = DmmSession(root=self.root)
        self.assertEqual(loaded.auth['accessToken'], 'renewed-A')
        self.assertEqual(loaded.http.cookies.get('session'), 'renewed-A')

    def test_missing_selected_file_never_falls_back_to_other_account(self):
        _, b, _ = self.two_accounts()
        self.store.path(b['key']).unlink()
        with self.assertRaises(DmmError):
            DmmSession(root=self.root)

    def test_cookie_renewal_wrong_identity_preserves_selected_snapshot(self):
        self.fixture(self.root, 'token-A', 'viewer-A')
        a = self.store.save_current('1', '账号一')
        session = DmmSession(root=self.root)
        old = self.store.path(a['key']).read_bytes()

        def renew(candidate, interactive):
            self.assertFalse(interactive)
            candidate.auth = {'accessToken': 'unexpected-B'}
            candidate.save()

        with patch.object(DmmSession, 'authenticated', return_value=False), \
                patch.object(DmmSession, 'login', renew), \
                patch.object(DmmSession, 'verify_game_identity', lambda candidate: candidate.accept_identity('viewer-B')), \
                self.assertRaises(DmmError):
            session.ensure_login()
        self.assertEqual(self.store.path(a['key']).read_bytes(), old)

    def test_missing_active_cache_does_not_import_current_dmm_account(self):
        self.fixture(self.root, 'token-A', 'viewer-A')
        self.store.save_current('1', '账号一')
        (self.root / 'session.dpapi').unlink()
        session = DmmSession(root=self.root)
        with patch.object(session, 'authenticated', return_value=True), patch.object(session, 'import_player') as imported:
            session.ensure_login()
        imported.assert_not_called()


if __name__ == '__main__':
    unittest.main()
