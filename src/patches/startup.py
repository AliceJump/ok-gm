"""Narrow compatibility fixes for ok-script 2.0.8."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from functools import wraps
from pathlib import Path

import pywintypes

_installed = False


def execute_game(game_cmd, arguments=None, start_method=None):
    import ok.util.process as process
    from src.dmm.helper import windows_args
    from src.dmm.launcher import launch_game, resolve_game_exe
    from src.dmm.session import DmmError
    if not game_cmd:
        return None
    if '://' in game_cmd:
        return _original_execute(game_cmd, arguments, start_method=start_method or process.WINDOWS_START_METHOD_START)
    game_path = process.get_path(game_cmd)
    if Path(game_path).name.casefold() == 'gakumas.exe' and Path(game_path).resolve() == Path(resolve_game_exe()).resolve():
        # Keep update and fresh credential acquisition inside the native start
        # pipeline. No secret arguments cross the framework's logging/shell code.
        from ok import og
        from src.ui.launcher_events import publish_progress, publish_download
        logger = process.logger

        def report(message):
            logger.info(message)
            publish_progress(message)

        exit_event = og.ok.exit_event
        launch_task = getattr(og.executor, 'current_task', None)

        def cancelled():
            stopped_task = getattr(launch_task, 'running', False) and not getattr(launch_task, 'enabled', True)
            if exit_event.is_set() or stopped_task:
                from src.dmm.session import OperationCancelled
                raise OperationCancelled('启动已取消')

        try:
            launch_game(progress=report, cancel_check=cancelled, download_progress=publish_download)
            return True
        except DmmError as error:
            publish_progress(str(error))
            raise
    if not Path(game_path).is_file():
        return None
    try:
        _, args = process._split_game_command(game_cmd, game_path, arguments)
        directory = str(Path(game_path).parent)
        if start_method == process.WINDOWS_START_METHOD_OS_STARTFILE:
            process.os.startfile(game_path, 'open', args or '', directory, 5)
        else:
            process.subprocess.Popen([game_path, *windows_args(args)], cwd=directory, shell=False,
                                     stdout=process.subprocess.DEVNULL, stderr=process.subprocess.DEVNULL,
                                     creationflags=getattr(process.subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
        return True
    except OSError:
        process.logger.error('Game process could not be created')
        return None


def install_startup_patches():
    global _installed, _original_execute
    from src.patches.task_config_lock import install_task_config_lock
    install_task_config_lock()
    if _installed:
        return
    import ok.util.process as process
    from ok.core import start_controller
    import ok.util.window as window
    from ok.device.capture_methods import hwnd_window
    from ok.ui.overlay import win32_gdi

    _original_execute = process.execute
    process.execute = execute_game
    start_controller.execute = execute_game

    # A window may disappear between EnumWindows and the subsequent lookup.
    original_find = window.find_hwnd

    @wraps(original_find)
    def safe_find(*args, **kwargs):
        try:
            return original_find(*args, **kwargs)
        except pywintypes.error as error:
            if getattr(error, 'winerror', None) == 1400 or (error.args and error.args[0] == 1400):
                return None, 0, None, 0, 0, 0, 0, []
            raise

    window.find_hwnd = hwnd_window.find_hwnd = safe_find

    # Upstream uses a distinct POINT type on the shared ctypes.windll functions;
    # pyautogui/pynput pass wintypes.POINT and otherwise fail argument validation.
    point_ptr = ctypes.POINTER(wintypes.POINT)
    win32_gdi.POINT = wintypes.POINT
    ctypes.windll.user32.GetCursorPos.argtypes = [point_ptr]
    ctypes.windll.user32.UpdateLayeredWindow.argtypes = [ctypes.c_void_p, ctypes.c_void_p, point_ptr,
        ctypes.POINTER(win32_gdi.SIZE), ctypes.c_void_p, point_ptr, wintypes.DWORD,
        ctypes.POINTER(win32_gdi.BLENDFUNCTION), wintypes.DWORD]
    ctypes.windll.gdi32.MoveToEx.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, point_ptr]
    _installed = True
