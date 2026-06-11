import os
import re
import sys
import time
import subprocess
import psutil
import pywintypes
import win32gui
import win32process
import ok.util.window as ok_window

from pathlib import Path

from src.tasks.BaseGMTask import BaseGMTask
from qfluentwidgets import FluentIcon


GAME_EXE = "gakumas.exe"
GAME_HWND_CLASS = "UnityWndClass"


def _is_invalid_hwnd_error(error):
    return (
        getattr(error, "winerror", None) == 1400
        or (getattr(error, "args", None) and error.args[0] == 1400)
    )


def _install_safe_find_hwnd():
    original_find_hwnd = getattr(
        ok_window.find_hwnd,
        "_ok_gm_original_find_hwnd",
        ok_window.find_hwnd
    )

    if getattr(ok_window.find_hwnd, "_ok_gm_safe_find_hwnd", False):
        safe_find_hwnd = ok_window.find_hwnd
    else:
        def safe_find_hwnd(*args, **kwargs):
            try:
                return original_find_hwnd(*args, **kwargs)
            except pywintypes.error as error:
                if _is_invalid_hwnd_error(error):
                    return None, 0, None, 0, 0, 0, 0, []
                raise

        safe_find_hwnd._ok_gm_safe_find_hwnd = True
        safe_find_hwnd._ok_gm_original_find_hwnd = original_find_hwnd
        ok_window.find_hwnd = safe_find_hwnd

    hwnd_window = sys.modules.get("ok.device.capture_methods.hwnd_window")
    if hwnd_window is not None:
        hwnd_window.find_hwnd = safe_find_hwnd


_install_safe_find_hwnd()


class LauncherTask(BaseGMTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.name = "Start Game"
        self.icon = FluentIcon.SYNC
        self.enable_after_start = True
        self.visible = False

    def run(self):

        try:
            self.log_info("开始启动游戏")
            if self._wait_for_game_window(timeout=3):
                self.log_info("检测到游戏已经运行")
                return True

            log_file = (
                Path(os.environ["APPDATA"])
                / "dmmgameplayer5"
                / "logs"
                / "dll.log"
            )

            self.log_info(f"DMM日志路径: {log_file}")

            if not log_file.exists():
                self.log_error("DMMGamePlayer 日志不存在")
                return False

            last_launch_line = None

            with open(
                log_file,
                "r",
                encoding="utf-8",
                errors="ignore"
            ) as f:

                for line in f:
                    if "Execute of:: gakumas exe" in line:
                        last_launch_line = line.strip()

            if not last_launch_line:
                self.log_error("未找到 gakumas 启动记录")
                return False

            self.log_info(last_launch_line)

            pattern = re.compile(
                r'exe:\s*(?P<exe_path>.*?gakumas\.exe).*?'
                r'/viewer_id=(?P<viewer_id>[^\s]+).*?'
                r'/open_id=(?P<open_id>[^\s]+).*?'
                r'/pf_access_token=(?P<pf_token>[^\s]+)',
                re.IGNORECASE
            )

            match = pattern.search(last_launch_line)

            if not match:
                self.log_error("启动参数解析失败")
                return False

            exe_path = match.group("exe_path").strip().strip('"')

            viewer_id = match.group("viewer_id")
            open_id = match.group("open_id")
            pf_token = match.group("pf_token")

            self.log_info(f"exe={exe_path}")

            if not os.path.exists(exe_path):
                self.log_error(f"exe不存在: {exe_path}")
                return False

            working_dir = os.path.dirname(exe_path)

            arg_string = (
                f"/viewer_id={viewer_id} "
                f"/open_id={open_id} "
                f"/pf_access_token={pf_token}"
            )

            #
            # 启动游戏
            #
            self.log_info("启动 gakumas.exe")

            process = subprocess.Popen(
                f'"{exe_path}" {arg_string}',
                cwd=working_dir,
                shell=True
            )

            self.log_info(f"PID={process.pid}")

            #
            # 等待窗口出现
            #
            self.log_info("等待 Unity 窗口创建")

            if not self._wait_for_game_window(timeout=180):
                self.log_error("等待游戏窗口超时")
                return False

            self.log_info("发现游戏窗口")

            return True

        except Exception as e:
            import traceback

            self.log_error(str(e))
            self.log_error(traceback.format_exc())

            return False

    def _wait_for_game_window(self, timeout=120):

        start = time.time()

        while time.time() - start < timeout:

            hwnd = self._find_game_window()

            if hwnd:
                self.log_info(f"发现窗口 hwnd={hwnd}")
                return True

            time.sleep(1)

        return False

    def _find_game_window(self):

        game_pid = None

        for proc in psutil.process_iter(
            ["pid", "name"]
        ):
            try:
                if (
                    proc.info["name"]
                    and proc.info["name"].lower()
                    == GAME_EXE.lower()
                ):
                    game_pid = proc.info["pid"]
                    break
            except Exception:
                pass

        if not game_pid:
            return 0

        found = []

        def enum_callback(hwnd, _):

            if not win32gui.IsWindow(hwnd):
                return True

            try:
                _, pid = (
                    win32process
                    .GetWindowThreadProcessId(hwnd)
                )

                if pid != game_pid:
                    return True

                if (
                    win32gui.GetClassName(hwnd)
                    != GAME_HWND_CLASS
                ):
                    return True

                found.append(hwnd)

            except Exception:
                pass

            return True

        win32gui.EnumWindows(
            enum_callback,
            None
        )

        return found[0] if found else 0
