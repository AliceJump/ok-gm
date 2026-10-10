import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication
from ok import og
from src.config import DMM_AUTO_UPDATE_KEY, DMM_ENABLED_KEY, DMM_PROXY_KEY
from src.dmm.session import LoginRequired
from src.dmm.xray import NODE_ENABLED_KEY
from src.ui.DmmLauncherTab import DmmLauncherTab, LauncherWorker


class LauncherUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_page_edits_the_same_settings_used_by_framework(self):
        settings = {DMM_PROXY_KEY: 'http://127.0.0.1:10808', DMM_ENABLED_KEY: True, DMM_AUTO_UPDATE_KEY: True}
        global_config = Mock()
        global_config.get_config.return_value = settings
        with patch.object(og, 'global_config', global_config):
            page = DmmLauncherTab()
        self.addCleanup(page.deleteLater)
        page.proxy.setText('http://127.0.0.1:10809')
        self.assertTrue(page.save_settings())
        page.auto_update.setChecked(False)
        self.assertEqual(settings[DMM_PROXY_KEY], 'http://127.0.0.1:10809')
        self.assertFalse(settings[DMM_AUTO_UPDATE_KEY])
        page.fixed_node.setChecked(True)
        self.assertTrue(settings[NODE_ENABLED_KEY])
        page.proxy.setText('http://127.0.0.1:invalid')
        self.assertFalse(page.save_settings())
        self.assertEqual(settings[DMM_PROXY_KEY], 'http://127.0.0.1:10809')

    def test_expired_update_session_logs_in_then_retries_update(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            helper = Mock()
            helper.session.root = root
            helper.prepare.side_effect = [LoginRequired('expired'), SimpleNamespace(version='3.4.1')]
            worker = LauncherWorker('update', 'http://127.0.0.1:10808', True)
            successes, failures = [], []
            worker.succeeded.connect(successes.append)
            worker.failed.connect(failures.append)
            with patch('src.ui.DmmLauncherTab.data_dir', return_value=root), \
                    patch('src.ui.DmmLauncherTab.DmmHelper', return_value=helper), \
                    patch('src.ui.DmmLauncherTab.restore_browser_proxy'), \
                    patch('src.ui.DmmLauncherTab.browser_login') as login:
                worker.run()
            login.assert_called_once()
            self.assertEqual(helper.prepare.call_count, 2)
            self.assertFalse(failures)
            self.assertIn('3.4.1', successes[0])

    def test_cancelled_worker_never_starts_browser_login(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            helper = Mock()
            helper.session.root = root
            worker = LauncherWorker('login', 'http://127.0.0.1:10808', True)
            failures = []
            worker.failed.connect(failures.append)
            worker.cancel()
            with patch('src.ui.DmmLauncherTab.data_dir', return_value=root), \
                    patch('src.ui.DmmLauncherTab.DmmHelper', return_value=helper), \
                    patch('src.ui.DmmLauncherTab.restore_browser_proxy'), \
                    patch('src.ui.DmmLauncherTab.browser_login') as login:
                worker.run()
            login.assert_not_called()
            self.assertIn('取消', failures[0])

    def test_switch_is_offline_and_never_starts_xray_or_authentication(self):
        with tempfile.TemporaryDirectory() as directory:
            worker = LauncherWorker('account-switch', 'http://127.0.0.1:10808', True, number='2',
                                    settings={DMM_PROXY_KEY: 'http://127.0.0.1:10808', NODE_ENABLED_KEY: True})
            successes = []
            worker.succeeded.connect(successes.append)
            with patch('src.ui.DmmLauncherTab.data_dir', return_value=Path(directory)), \
                    patch('src.ui.DmmLauncherTab.AccountStore') as store, \
                    patch('src.ui.DmmLauncherTab.operation_proxy') as proxy:
                store.return_value.switch.return_value = {'number': '2', 'name': '账号二'}
                worker.run()
            store.return_value.switch.assert_called_once_with('2')
            proxy.assert_not_called()
            self.assertIn('账号二', successes[0])

    def test_duplicate_new_account_id_is_rejected_before_opening_browser(self):
        with tempfile.TemporaryDirectory() as directory:
            worker = LauncherWorker('account-login', 'http://127.0.0.1:10808', True, number='1', name='账号一')
            failures = []
            worker.failed.connect(failures.append)
            with patch('src.ui.DmmLauncherTab.data_dir', return_value=Path(directory)), \
                    patch('src.ui.DmmLauncherTab.AccountStore') as store, \
                    patch('src.ui.DmmLauncherTab.ensure_game_stopped'), \
                    patch('src.ui.DmmLauncherTab.operation_proxy') as proxy:
                store.return_value.read.return_value = {'accounts': [{'number': '1'}]}
                worker.run()
            proxy.assert_not_called()
            self.assertIn('新的编号', failures[0])


if __name__ == '__main__':
    unittest.main()
