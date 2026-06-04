import re
import time
import pyautogui
from qfluentwidgets import FluentIcon
from src.data.FeatureList import FeatureList as fL
from src.tasks.daily.step.daily_shop import DailyShop
from src.tasks.BaseGMTask import BaseGMTask
from src.interaction.Mouse import run_at_window_pos
from src.tasks.mixin.shop_mixin import ShopMixin
from src.tasks.daily.step.daily_coin_random import DailyCoinRandom

class TestTask(BaseGMTask, DailyCoinRandom, ShopMixin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "测试任务"
        self.description = "这是一个测试任务，用于测试一些功能。"
        self.icon = FluentIcon.UP
    def run(self):
       self.ensure_main()
       self.go_coin_random()


