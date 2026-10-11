import tempfile
import threading
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication
from qfluentwidgets import FluentIcon
from ok import Config, og
from src.dmm.accounts import AccountStore
from src.dmm.session import DmmSession
from src.tasks.BaseGMTask import BaseGMTask
from src.tasks.account import account_scope_store as scope
from src.tasks.mixin.account_override_mixin import AccountOverrideMixin
from src.ui.AccountConfigTab import AccountConfigTab


class Task(AccountOverrideMixin):
    def __init__(self, folder):
        self.default_config = {'竞技场': True, '次数': 1, '多账户独立配置': True}
        self.config = Config('FixtureTask', self.default_config, folder=str(folder))
        self.config_type, self.config_description = {}, {}
        self.name, self.icon, self.running = 'FixtureTask', FluentIcon.SETTING, False
        self.current_account_id = self.current_user = ''
        self._bind_account_aware_config_get()


class AccountTaskConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        directory = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.root = Path(directory)
        self.stack.enter_context(patch('src.dmm.helper.ensure_game_stopped'))
        self.stack.enter_context(patch('src.dmm.session.data_dir', return_value=self.root))
        self.stack.enter_context(patch('src.ui.AccountConfigTab.data_dir', return_value=self.root))
        self.stack.enter_context(patch.object(scope, 'get_store_path', return_value=str(self.root / 'overrides.json')))
        scope.load_overrides(force=True)
        self.store = AccountStore(self.root)
        for number in ['1', '2']:
            session = DmmSession(root=self.root / ('fixture' + number))
            session.auth = {'accessToken': 'fixture-' + number}
            session.save()
            self.store.save_current(number, '账号' + number, session.path, new=True)
        scope.bind_dmm_accounts(self.store.read()['accounts'])

    def test_runtime_uses_selected_account_and_never_changes_base_config(self):
        task = Task(self.root)
        scope.set_account_task_overrides(scope.dmm_account_id('1'), 'Task', {'竞技场': False, '次数': 3})
        scope.set_account_task_overrides(scope.dmm_account_id('2'), 'Task', {'竞技场': True, '次数': 5})
        self.store.switch('1')
        task.running = True
        self.assertFalse(task.config.get('竞技场'))
        self.assertEqual(task.config.get('次数'), 3)
        self.store.switch('2')
        self.assertEqual(task.config.get('次数'), 5)
        task.running = False
        self.assertEqual(task.config.get('次数'), 1)
        self.assertTrue(task.config.get('竞技场'))

    def test_snapshot_replacement_and_rename_preserve_task_configuration(self):
        key = scope.dmm_account_id('1')
        scope.set_account_task_overrides(key, 'Task', {'次数': 7})
        self.store.switch('1')
        old_key = self.store.active()['key']
        self.store.save_current('1', '新名称')
        self.assertNotEqual(old_key, self.store.active()['key'])
        scope.bind_dmm_accounts(self.store.read()['accounts'])
        self.assertEqual(scope.get_account_task_overrides(key, 'Task'), {'次数': 7})

    def test_batch_switches_login_files_before_yielding_task_context(self):
        task = object.__new__(BaseGMTask)
        task.config = Config('BatchFixture', {'多账户模式': True, '多账户独立配置': True, '账号列表': '2\n1'}, folder=str(self.root))
        task.current_user = task.current_account_id = ''
        task.log_info = Mock()
        transitions = []

        def switch(number):
            self.store.switch(number)
            transitions.append(number)

        task.switch_task_account = switch
        rounds = []
        for index, total in task.iter_multi_account_context():
            rounds.append((index, total, task.current_account_id, DmmSession(root=self.root).auth['accessToken']))
        self.assertEqual(transitions, ['2', '1'])
        self.assertEqual(rounds, [(0, 2, 'dmm_2', 'fixture-2'), (1, 2, 'dmm_1', 'fixture-1')])

    def test_account_editor_saves_separate_snapshots_and_locks_while_running(self):
        task = Task(self.root)
        with patch.object(og, 'app', SimpleNamespace(tr=lambda s: s)):
            page = AccountConfigTab()
            self.addCleanup(page.deleteLater)
            page.executor = SimpleNamespace(get_all_tasks=lambda: [task])
            page.refresh()
            self.assertIsNotNone(page.editor)
            page.account_selector.setCurrentIndex(0)
            page.virtual_config['次数'] = 3
            page.save_current()
            page.account_selector.setCurrentIndex(1)
            page.virtual_config['次数'] = 5
            page.save_current()
            task.running = True
            page.update_lock()
            self.assertFalse(page.save_button.isEnabled())
            self.assertFalse(page.editor.isEnabled())
        self.assertEqual(scope.get_account_task_overrides('dmm_1', 'Task')['次数'], 3)
        self.assertEqual(scope.get_account_task_overrides('dmm_2', 'Task')['次数'], 5)
        self.assertEqual(task.config.get('次数'), 5)  # Selected account 2, runtime only.
        task.running = False
        self.assertEqual(task.config.get('次数'), 1)

    def test_framework_task_after_init_binds_context_before_run_and_clears_it(self):
        class Probe(BaseGMTask):
            def run(self):
                return self.current_account_id

        executor = SimpleNamespace(scene=None, debug=False, exit_event=threading.Event())
        app = SimpleNamespace()
        with patch.object(Config, 'config_folder', str(self.root)):
            task = Probe(executor=executor, app=app)
            task.after_init()
        self.assertEqual(task.run(), 'dmm_2')
        self.assertEqual(task.current_account_id, '')

    def test_batch_switch_closes_then_switches_then_restarts_native_capture(self):
        task = object.__new__(BaseGMTask)
        task._enabled = True
        calls = []
        task._executor = SimpleNamespace(exit_event=threading.Event(), reset_scene=lambda: calls.append('capture-reset'))
        controller = Mock()
        controller.start_device.side_effect = lambda **kw: calls.append('native-start-' + DmmSession(root=self.root).auth['accessToken']) or True
        task._app = SimpleNamespace(start_controller=controller)
        task.log_info = Mock()
        manager = Mock()
        manager.do_refresh.side_effect = lambda *args: calls.append('refresh')
        switch = AccountStore.switch

        def record_switch(store, number):
            calls.append('switch-' + number)
            return switch(store, number)

        with patch.object(og, 'device_manager', manager), \
                patch('src.dmm.helper.close_game', side_effect=lambda *args: calls.append('close')), \
                patch.object(AccountStore, 'switch', record_switch):
            task.switch_task_account('1')
        self.assertEqual(calls, ['close', 'switch-1', 'refresh', 'native-start-fixture-1', 'capture-reset'])

    def test_game_close_failure_preserves_login_slot_and_stops_restart(self):
        from src.dmm.session import DmmError
        task = object.__new__(BaseGMTask)
        task._enabled = True
        task._executor = SimpleNamespace(exit_event=threading.Event())
        task._app = SimpleNamespace(start_controller=Mock())
        task.log_info = Mock()
        old = self.store.index.read_bytes()
        with patch('src.dmm.helper.close_game', side_effect=DmmError('still running')), self.assertRaises(DmmError):
            task.switch_task_account('1')
        self.assertEqual(self.store.index.read_bytes(), old)
        task._app.start_controller.start_device.assert_not_called()


if __name__ == '__main__':
    unittest.main()
