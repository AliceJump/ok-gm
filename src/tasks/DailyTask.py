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
from src.tasks.daily.step.daily_shop import DailyShop
from src.tasks.daily.step.daily_up_card import DailyUpCard
from src.tasks.daily.step.daily_reward import DailyReward
from src.tasks.daily.step.daily_coin_random import DailyCoinRandom
from src.tasks.mixin.shop_mixin import ShopMixin
from src.data.FeatureList import FeatureList as fL

class DailyTask(
    DailyArena, DailyGift, DailyWork, 
    DailyCreditCollect, DailyShop, DailyUpCard, 
    DailyReward, DailyCoinRandom,
    ShopMixin, 
    BaseGMTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "日常任务"
        self.description = "自动完成日常任务，包括竞技场、收小礼物、打工和收米等。"
        self.icon = FluentIcon.SYNC
        self.daily_runner: DailyTaskRunner | None = None
        self.support_schedule_task = True
        self.init_config()

    def init_config(self):
        self.default_config.update({key: True for key, _ in self.build_task_plan()})
        self.default_config["购买角色碎片"] = False
        self.config_description.update({
            "购买角色碎片": "是否在日常商店购买角色碎片",
        })
        self.config_description.update({
            "竞技场": "是否自动参与竞技场挑战",
            "收小礼物": "是否自动领取日常礼物奖励",
            "打工": "执行小偶像打工任务获取资源",
            "收米": "领取收益/金币类奖励",
            "商店": "进入商店执行日常购买操作",
            "升级卡片": "升级一次支援卡",
            "领取奖励": "领取日常周常奖励",
            "购买角色碎片": "是否在商店任务购买角色碎片",
        })

    def build_task_plan(self):
        return [
            ("竞技场", self.go_arena),
            ("收小礼物", self.go_gift),
            ("打工", self.go_work),
            ("收米", self.go_credit_collect),
            ("商店", self.go_shop),
            ("升级卡片", self.go_up_card),
            ("_小偶像硬币抽奖", self.go_coin_random),
            ("领取奖励", self.go_reward),
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