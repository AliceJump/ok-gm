import ctypes
import tempfile
import threading
import unittest
from ctypes import wintypes
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ok import og
from ok.core.start_controller import StartController
from src.config import config
from src.dmm.helper import DmmHelper
from src.dmm.session import DmmError
from src.patches.startup import execute_game, install_startup_patches


class FrameworkLaunchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.exe = Path(self.temp.name) / 'gakumas.exe'
        self.exe.write_bytes(b'test executable')

    def test_native_controller_launches_before_waiting_and_without_legacy_task(self):
        self.assertTrue(config['windows']['start_exe'])
        self.assertFalse(any(item[1] == 'LauncherTask' for item in config['onetime_tasks']))
        controller = object.__new__(StartController)
        controller.config = config
        controller.exit_event = threading.Event()
        controller.start_method = 'start'
        controller.tr = lambda message: message
        calls = []
        manager = Mock()
        manager.get_preferred_device.return_value = {'device': 'windows', 'connected': False}
        manager.get_exe_path.return_value = str(self.exe)
        controller._wait_until_started_window_stable = lambda: calls.append('window') or True
        controller._wait_until_device_ready = lambda: calls.append('capture') or True
        globals_config = Mock()
        globals_config.get_config.return_value = {}
        with patch.object(og, 'device_manager', manager), patch.object(og, 'global_config', globals_config), \
                patch.object(og, 'ok', SimpleNamespace(exit_event=controller.exit_event)), \
                patch('ok.core.start_controller.is_admin', return_value=True), \
                patch('src.dmm.launcher.resolve_game_exe', return_value=str(self.exe)), \
                patch('src.dmm.launcher.launch_game', side_effect=lambda **kwargs: calls.append('update-and-launch')):
            self.assertTrue(controller.start_device())
        self.assertEqual(calls, ['update-and-launch', 'window', 'capture'])

    def test_update_finishes_then_fetches_fresh_arguments_before_creating_process(self):
        helper = object.__new__(DmmHelper)
        helper.session = SimpleNamespace(root=Path(self.temp.name))
        helper.progress = lambda message: None
        old = SimpleNamespace(exe=self.exe, arguments=['/pf_access_token=old'], version='new',
                              plan=Mock(root=self.exe.parent))
        fresh = SimpleNamespace(exe=self.exe, arguments=['/pf_access_token=fresh'], plan=Mock())
        old.plan.pending.return_value = ['needs update']
        fresh.plan.pending.return_value = []
        calls = []
        updater = Mock()
        updater.run.side_effect = lambda: calls.append('update')
        helper.updater = Mock(return_value=updater)

        def fetch():
            calls.append('fetch')
            return old if len(calls) == 1 else fresh

        helper.fetch = fetch
        with patch('src.dmm.helper.ensure_game_stopped'), patch('src.dmm.helper.ensure_update_idle'), \
                patch('src.dmm.helper.subprocess.Popen', side_effect=lambda *args, **kwargs: calls.append('process') or Mock(pid=1)) as popen:
            helper.launch()
        self.assertEqual(calls, ['fetch', 'update', 'fetch', 'process'])
        self.assertEqual(popen.call_args.args[0], [str(self.exe), '/pf_access_token=fresh'])
        self.assertFalse(popen.call_args.kwargs['shell'])

    def test_update_failure_prevents_process_creation(self):
        helper = object.__new__(DmmHelper)
        helper.prepare = Mock(side_effect=DmmError('download failed'))
        with patch('src.dmm.helper.subprocess.Popen') as popen, self.assertRaises(DmmError):
            helper.launch()
        popen.assert_not_called()

    def test_standard_cursor_position_works_after_idempotent_patch(self):
        import ok.util.process as process
        from ok.ui.overlay import win32_gdi
        installed = process.execute
        install_startup_patches()
        self.assertIs(process.execute, installed)
        self.assertIs(win32_gdi.POINT, wintypes.POINT)
        self.assertTrue(ctypes.windll.user32.GetCursorPos(ctypes.byref(wintypes.POINT())))
        import pyautogui
        self.assertEqual(len(pyautogui.position()), 2)

    def test_other_executables_use_argv_and_no_unread_pipe(self):
        other = self.exe.with_name('other.exe')
        other.write_bytes(b'test')
        with patch('ok.util.process.subprocess.Popen') as popen:
            self.assertTrue(execute_game(str(other), arguments='"two words" a&b'))
        self.assertEqual(popen.call_args.args[0], [str(other), 'two words', 'a&b'])
        self.assertFalse(popen.call_args.kwargs['shell'])
        self.assertEqual(popen.call_args.kwargs['stdout'], -3)

    def test_os_startfile_accepts_empty_arguments(self):
        import ok.util.process as process
        other = self.exe.with_name('other.exe')
        other.write_bytes(b'test')
        with patch('ok.util.process.os.startfile') as start:
            self.assertTrue(execute_game(str(other), start_method=process.WINDOWS_START_METHOD_OS_STARTFILE))
        self.assertEqual(start.call_args.args[2], '')

    def test_account_config_override_still_works_with_new_framework(self):
        from ok import Config
        from src.tasks.mixin.account_override_mixin import AccountOverrideMixin

        class Task(AccountOverrideMixin):
            current_account_id = 'compatibility-test'
            current_user = 'test'

        task = Task()
        task.running = True
        task.config = Config('compatibility', {'多账户独立配置': True, 'enabled': True}, folder=self.temp.name)
        with patch('src.tasks.mixin.account_override_mixin.get_account_task_overrides', return_value={'enabled': False}):
            task._bind_account_aware_config_get()
            task._bind_account_aware_config_get()
            self.assertFalse(task.config.get('enabled'))
            self.assertTrue(task._raw_cfg_get('enabled'))
            task.running = False
            self.assertTrue(task.config.get('enabled'))
            task.running = True
            task.config['多账户独立配置'] = False
            self.assertTrue(task.config.get('enabled'))


if __name__ == '__main__':
    unittest.main()
