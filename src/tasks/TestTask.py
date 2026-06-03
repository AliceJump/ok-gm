import time
from qfluentwidgets import FluentIcon
from src.data.FeatureList import FeatureList as fL
from src.tasks.daily.step.daily_shop import DailyShop
from src.tasks.BaseGMTask import BaseGMTask
from src.interaction.Mouse import run_at_window_pos
from src.tasks.mixin.shop_mixin import ShopMixin

class TestTask(BaseGMTask, DailyShop, ShopMixin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "测试任务"
        self.description = "这是一个测试任务，用于测试一些功能。"
        self.icon = FluentIcon.UP
    def run(self):
        self.ensure_main()
        # self.wait_click_feature(feature=fL.task_enter, raise_if_not_found=False, click_after_delay=0.5)
        # self.wait_ui_stable()
        # splits = self.find_feature(feature_name=[fL.split_icon], box=self.box_of_screen(0.037, 0.740, 0.961, 0.795))
        # if splits:
        #     self.log_info(f"找到了{len(splits)}个分割线")
        #     for i in range(len(splits)):
        #         splits[i].x -= int((0.407-0.319)*self.screen_width)
        # else:
        #     self.log_info("没有找到分割线")
        # times = 0
        # for split in splits:
        #     if times >= 2:
        #         self.log_info("点击了两次分割线了，不可能再点了")
        #         break
        #     self.click(split, after_sleep=0.5)
        #     self.wait_ui_stable()
        #     times += 1
        #     self.wait_click_feature(feature=fL.next_step, vertical_variance=0.1, horizontal_variance=0.1, raise_if_not_found=False, click_after_delay=0.5)
        #     for _ in range(2):
        #         if not self.click_close(after_sleep=0.5):
        #             break

            