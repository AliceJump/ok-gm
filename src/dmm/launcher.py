"""Shared game launch service used by the framework and the launcher page."""
from __future__ import annotations

import os
import subprocess
import uuid
from contextlib import contextmanager
from pathlib import Path

import psutil

from src.dmm.browser_proxy import restore_browser_proxy
from src.dmm.helper import DmmHelper, ensure_game_stopped, helper_lock, windows_args
from src.dmm.session import DmmError, LoginRequired, DmmSession, atomic_write, data_dir


def resolve_game_exe(_detected_path=None):
    root, _ = DmmHelper.installed_game()
    return str(root / 'gakumas.exe')


def start_vpn(progress=lambda message: None):
    from ok import og
    from src.config import VPN_CONFIG_NAME, VPN_START_PATH_KEY, VPN_WORKING_DIRECTORY_KEY
    if og.global_config is None:
        return
    config = og.global_config.get_config(VPN_CONFIG_NAME)
    path = config.get(VPN_START_PATH_KEY, '').strip()
    if not path:
        return
    target = Path(path).resolve()
    if not target.is_file():
        raise DmmError('VPN 启动路径不存在，请检查 VPN 设置')
    for process in psutil.process_iter(['exe']):
        try:
            if process.info['exe'] and Path(process.info['exe']).resolve() == target:
                return
        except (psutil.Error, OSError):
            continue
    directory = config.get(VPN_WORKING_DIRECTORY_KEY, '').strip() or str(target.parent)
    if not Path(directory).is_dir():
        raise DmmError('VPN 工作目录不存在，请检查 VPN 设置')
    try:
        subprocess.Popen([str(target)], cwd=directory, shell=False)
    except OSError:
        raise DmmError('VPN 启动失败，请检查 VPN 设置') from None
    progress('已启动 VPN 客户端')


def _browser_login(helper, progress, browser='system'):
    try:
        helper.session.login(browser=browser)
    except LoginRequired as error:
        if '授权码签发失败' not in str(error):
            raise
        # The remembered browser protocol handler may have already delivered the
        # code to DMM Player. Only retain/import a server-verified credential.
        if not helper.session.authenticated():
            helper.session.import_player()
            if not helper.session.authenticated():
                raise error
        progress('有效登录态已保存')


@contextmanager
def login_candidate(helper, fresh=False):
    original = helper.session
    base = original.root
    pending = base / 'pending' / uuid.uuid4().hex
    pending.mkdir(parents=True)
    if not fresh and original.accounts.current_path().exists():
        atomic_write(pending / 'session.dpapi', original.accounts.current_path().read_bytes())
    candidate = DmmSession(original.proxy, pending)
    candidate.proxy_root = original.proxy_root
    candidate.progress = original.progress
    candidate.cancel_check = original.cancel_check
    helper.session = candidate
    try:
        yield candidate
    finally:
        helper.session = original
        # Delete only this operation's known staging file, never account backups.
        (pending / 'session.dpapi').unlink(missing_ok=True)
        try:
            pending.rmdir()
        except OSError:
            pass


def _adopt(original, candidate):
    original.auth = candidate.auth
    original.device = candidate.device
    original.identity = candidate.identity
    original.http.cookies.clear()
    original.http.cookies.update(candidate.http.cookies)
    original.save()


def browser_login(helper, progress=lambda message: None, browser='system'):
    original = helper.session
    if not original.profile_key:
        _browser_login(helper, progress, browser)
        return
    if not original.identity:
        try:
            original.verify_game_identity()
        except DmmError:
            raise LoginRequired('该快照尚未确认账号身份，请先使用原登录态启动一次，或重新登录并保存为新账号') from None
    progress('请确认浏览器登录的是当前所选账号；身份不符时不会覆盖存档')
    with login_candidate(helper) as candidate:
        _browser_login(helper, progress, browser)
        candidate.verify_game_identity()
        _adopt(original, candidate)


def import_login(helper):
    original = helper.session
    if not original.profile_key:
        return original.import_player()
    if not original.identity:
        original.verify_game_identity()
    with login_candidate(helper) as candidate:
        copied = candidate.import_player()
        candidate.verify_game_identity()
        _adopt(original, candidate)
        return copied


def launch_game(settings=None, progress=lambda message: None, cancel_check=lambda: None,
                download_progress=lambda done, total: None):
    from ok import og
    from src.config import DMM_CONFIG_NAME, DMM_PROXY_KEY, DMM_AUTO_UPDATE_KEY, DMM_ENABLED_KEY
    if settings is None:
        settings = og.global_config.get_config(DMM_CONFIG_NAME)
    with helper_lock(data_dir()):
        cancel_check()
        if any((p.info['name'] or '').casefold() == 'gakumas.exe' for p in psutil.process_iter(['name'])):
            progress('游戏已经运行')
            return None
        if not settings.get(DMM_ENABLED_KEY, True):
            return launch_legacy(progress)
        restore_browser_proxy(data_dir(), progress=progress)
        from src.dmm.xray import operation_proxy
        with operation_proxy(settings, progress, cancel_check) as proxy:
            helper = DmmHelper(proxy, progress, download_progress=download_progress)
            helper.session.cancel_check = cancel_check
            try:
                return helper.launch(settings.get(DMM_AUTO_UPDATE_KEY, True))
            except LoginRequired:
                progress('登录态需要续期，将打开常用浏览器')
                browser_login(helper, progress)
                return helper.launch(settings.get(DMM_AUTO_UPDATE_KEY, True))


def launch_legacy(progress):
    import re
    log = Path(os.environ['APPDATA']) / 'dmmgameplayer5/logs/dll.log'
    try:
        with log.open(encoding='utf-8', errors='ignore') as stream:
            record = next((line for line in reversed(stream.readlines()) if 'Execute of:: gakumas exe' in line), '')
        match = re.search(r'exe:\s*(.*?gakumas\.exe).*?(/viewer_id=\S+).*?(/open_id=\S+).*?(/pf_access_token=\S+)',
                          record, re.IGNORECASE)
        if not match:
            raise ValueError()
        exe = Path(match[1].strip().strip('"'))
        if exe.resolve() != Path(resolve_game_exe()).resolve():
            raise ValueError()
        ensure_game_stopped()
        process = subprocess.Popen([str(exe), *windows_args(' '.join(match.groups()[1:]))], cwd=exe.parent, shell=False,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, ValueError):
        raise DmmError('旧 DMM 启动记录不可用，请启用本地启动器并登录') from None
    progress('已使用旧 DMM 记录启动游戏（凭证已隐藏）')
    return process
