import re

from ok import BaseTask
from src.tasks.mixin.runtime_mixin import RuntimeMixin
from src.tasks.mixin.login_mixin import LoginMixin
from src.tasks.mixin.account_override_mixin import AccountOverrideMixin
class BaseGMTask(RuntimeMixin, LoginMixin, AccountOverrideMixin, BaseTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _logged_in = False

    def iter_multi_account_context(self, repeat_times: int = 1, empty_accounts_message: str | None = None,
                                   account_log_suffix: str = "", allow_multi_account: bool = True):
        """统一多账号执行上下文。

        当开启多账户模式时，会先读取账号列表；列表为空则直接结束当前任务。
        每次迭代前会自动设置当前账号、记录启动日志并执行登录流程。

        Args:
            repeat_times: 非多账户模式下的执行轮数。
            empty_accounts_message: 账号列表为空时的提示文案。
            account_log_suffix: 账号启动日志的后缀文本。

        Yields:
            tuple[int, int]: 当前轮次索引和总轮数。
        """
        accounts_bool = self.config.get("多账户模式", False) and allow_multi_account
        if accounts_bool:
            accounts_list = self.get_account_list()
            if not accounts_list:
                if empty_accounts_message:
                    self.log_info(empty_accounts_message, notify=True)
                return
            repeat_times = len(accounts_list)
        else:
            accounts_list = []

        for repeat_idx in range(repeat_times):
            if accounts_bool:
                account = accounts_list[repeat_idx]
                username = str(account.get("username", "")).strip()
                account_id = str(account.get("account_id", "")).strip() or username
                if not username:
                    self.log_info(f"第 {repeat_idx + 1}/{repeat_times} 个账号为空，已跳过")
                    continue

                self.set_current_account(username, account_id)
                self.log_info(f"开始第 {repeat_idx + 1}/{repeat_times} 个账号({username[-4:]}){account_log_suffix}")
                self.login_flow(username)
            else:
                self.set_current_account("", "")

            yield repeat_idx, repeat_times

    def mark_task_failure(self, message: str, task_name: str | None = None):
        """统一标记任务失败消息，并截图（包含时间和任务名称）。

        在日常任务编排器可用时写入 runner.failure_details；
        否则退化为普通日志，避免在独立任务中报错。
        """
        # 生成截图文件名：失败时间+任务名
        from datetime import datetime
        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = task_name or getattr(self, "current_task", None) or "UnknownTask"
        screenshot_name = f"fail_{now_str}_{name}"
        try:
            self.screenshot(screenshot_name)
        except Exception:
            pass

        runner = getattr(self, "daily_runner", None)
        if runner is not None and hasattr(runner, "set_task_failure"):
            runner.set_task_failure(message, task_name=task_name)
            return
        self.log_info(str(message))

    def set_current_account(self, username, account_id):
        """设置当前账号信息，供账号覆盖功能使用。

        调用时机：
            应在任何依赖账号覆盖的配置读取或任务执行前调用。通常在账号
            登录上下文已经确定、但尚未开始读取账号相关配置时设置。

        多次调用行为：
            允许重复调用。后一次调用会直接覆盖此前保存的
            ``self.current_user`` 和 ``self.current_account_id``，并重新执行
            ``_bind_account_aware_config_get()``，使后续配置获取逻辑以最新
            的账号信息为准。

        参数约束：
            username:
                当前账号对应的用户名/显示名，应为字符串。建议传入稳定、可
                识别的原始用户名，不要传入 ``None``、临时拼接值或仅用于显示
                的不稳定别名。
            account_id:
                当前账号的稳定唯一标识，应为字符串。账号覆盖逻辑优先使用该值，
                因此应尽量传入跨会话保持不变的账号ID，而不是可能变化的昵称、
                索引或临时标记。
        """
        self.current_user = username
        self.current_account_id = account_id
        self._bind_account_aware_config_get()

    