import re
import tempfile
import os
import webbrowser
from pathlib import Path
from qfluentwidgets import FluentIcon
from src.tasks.daily.finally_file import create_daily_summary_report
from src.tasks.BaseGMTask import BaseGMTask
from src.tasks.daily.daily_task_runner import DailyTaskRunner
from src.tasks.daily.step.daily_arena import DailyArena
from src.tasks.daily.step.daily_gift import DailyGift
from src.tasks.daily.step.daily_work import DailyWork
from src.tasks.daily.step.daily_credit_collect import DailyCreditCollect

class DailyTask(DailyArena, DailyGift, DailyWork, DailyCreditCollect, BaseGMTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "日常任务"
        self.description = "自动完成日常任务，包括竞技场、收小礼物、打工和收米等。"
        self.icon = FluentIcon.SYNC
        self.daily_runner: DailyTaskRunner | None = None
        self.init_config()

    def init_config(self):
        self.default_config.update({key: True for key, _ in self.build_task_plan()})

    def build_task_plan(self):
        return [
            ("竞技场", self.go_arena),
            ("收小礼物", self.go_gift),
            ("打工", self.go_work),
            ("收米", self.go_credit_collect),
        ]

    def run(self):
        """日常任务主入口。"""
        repeat_times = self.config.get("重复测试的次数", 1) if self.debug else 1
        try:
            self.daily_runner = DailyTaskRunner(self, self.build_task_plan())
            self.daily_runner.run(repeat_times=repeat_times)
        finally:
            self.run_daily_finally()
    def run_daily_finally(self):
        try:
            # 在任务完成或停止时自动生成一个临时的汇总文件并打开（不再依赖配置项）
            target_directory = Path(tempfile.gettempdir())

            # 仅在 runner 产生了有效汇总数据时才创建临时文件
            if not (self.daily_runner and self.daily_runner.has_summary_data()):
                # 若没有可用的汇总信息，则不创建也不打开临时文件
                self.log_info("无可用汇总信息，跳过生成临时汇总文件")
                return True

            summary_info = self.daily_runner.final_summary
            summary_path = create_daily_summary_report(target_directory, summary_info)

            # 立即用系统默认程序打开临时汇总文件
            self._open_local_path_with_default_app(summary_path)

            self.log_info(f"日常执行情况汇总已创建并打开: {summary_path}")

            return True
        except Exception as e:
            self.log_info(f"创建日常任务结尾文件失败: {e}", notify=True)
            return False
    def _open_local_path_with_default_app(self, path: str | Path):
        normalized_path = Path(path).resolve()
        file_uri = normalized_path.as_uri()
        if os.name == "nt":
            try:
                os.startfile(str(normalized_path))
                return
            except OSError as error:
                self.log_debug(f"使用 os.startfile 打开路径失败，改用浏览器回退: {error}")
        webbrowser.open(file_uri)