"""Run with the repository interpreter: python -m src.dmm check|login|update|launch."""
import argparse
import json
import sys

from src.dmm.helper import DmmHelper, helper_lock
from src.dmm.session import DEFAULT_PROXY, DmmError, LoginRequired, data_dir
from src.dmm.browser_proxy import restore_browser_proxy
from src.dmm.launcher import browser_login, import_login
from src.dmm.xray import NODE_ENABLED_KEY, operation_proxy
from src.config import DMM_PROXY_KEY


def main():
    parser = argparse.ArgumentParser(description="学园偶像大师本地 DMM 登录、更新、启动助手")
    parser.add_argument("command", choices=["status", "import", "login", "check", "update", "launch", "restore-proxy"])
    parser.add_argument("--proxy", default=DEFAULT_PROXY, help="本地 HTTP 代理入口")
    parser.add_argument("--no-update", action="store_true", help="需要更新时停止启动")
    parser.add_argument("--fixed-node", action="store_true", help="使用软件内已保存的独立 Xray 节点")
    parser.add_argument("--browser", choices=["system", "private"], default="system",
                        help="system 使用常用浏览器和已保存的密码；private 使用临时 Edge 窗口")
    args = parser.parse_args()
    try:
        progress = lambda message: print(message, flush=True)
        with helper_lock(data_dir()):
            recovered = restore_browser_proxy(data_dir(), progress=progress)
            if args.command == "restore-proxy":
                if not recovered:
                    print("没有待恢复的临时浏览器代理")
                return 0
            settings = {DMM_PROXY_KEY: args.proxy, NODE_ENABLED_KEY: args.fixed_node}
            with operation_proxy(settings, progress) as proxy:
                helper = DmmHelper(proxy, progress)
                execute(args, helper, progress)
        return 0
    except DmmError as error:
        print(str(error), file=sys.stderr, flush=True)
        return 1
    except KeyboardInterrupt:
        print("操作已中断；下载断点将在下次 update 时继续", file=sys.stderr)
        return 130
    except Exception as error:
        # Requests/OS/browser errors can contain signed URLs or launch arguments.
        print(f"助手操作失败（{type(error).__name__}），未输出敏感参数", file=sys.stderr)
        return 1


def execute(args, helper, progress):
    if args.command == "import":
        cookie_imported = import_login(helper)
        print("已复制 DMM 登录态并加密保存；DMM 原文件未改动")
        if not cookie_imported:
            print("DMM Cookie 数据库正在被占用，仅导入凭证；需要 Cookie 时请退出 DMM Player 后重新 import")
    elif args.command == "login":
        print("请在浏览器完成登录，不要把密码或验证码发送到聊天", flush=True)
        browser_login(helper, progress, browser=args.browser)
        print("登录态已加密保存")
    elif args.command == "status":
        if not helper.session.accounts.current_path().exists():
            raise LoginRequired("尚未保存登录态，请先 login 或 import")
        valid = helper.session.authenticated()
        print(json.dumps({"authenticated": valid, "cookie_count": len(helper.session.http.cookies)}, ensure_ascii=False))
    elif args.command == "check":
        helper.check()
    elif args.command == "update":
        helper.prepare(auto_update=True)
        print("游戏更新与文件校验完成")
    else:
        helper.launch(auto_update=not args.no_update)


if __name__ == "__main__":
    raise SystemExit(main())
