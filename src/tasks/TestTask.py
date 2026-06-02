from qfluentwidgets import FluentIcon
from src.data.FeatureList import FeatureList as fL
from src.tasks.daily.step.daily_arena import DailyArena
from src.tasks.BaseGMTask import BaseGMTask
from src.interaction.Mouse import run_at_window_pos

class TestTask(DailyArena, BaseGMTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "测试任务"
        self.description = "这是一个测试任务，用于测试一些功能。"
        self.icon = FluentIcon.UP
    def run(self):
        self.ensure_main()
        self.wait_click_feature
    