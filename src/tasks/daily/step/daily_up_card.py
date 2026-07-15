from src.data.FeatureList import FeatureList as fL
from src.tasks.BaseGMTask import BaseGMTask
class DailyUpCard(BaseGMTask):
    def go_up_card(self):
        self.log_info("开始升级支援卡...")
        if not self.wait_click_feature(feature=fL.switch_baby_page, raise_if_not_found=False, click_after_delay=0.5):
            self.mark_task_failure("找不到升级支援卡的门")
            return False
        if not self.click_feature(feature_name=fL.support_card_enter, time_out=4, click_after_delay=0.5, verify_timeout=2):
            self.mark_task_failure("找不到升级支援卡界面的进入按钮")
            return False
        if self.switch_order(target_order="up"):
            self.log_info("切换到升序成功")
        self.sleep(0.5)
        self.click(0.196, 0.373, after_sleep=0.5) # 点击第一个卡片
        if not self.click_feature(feature_name=fL.card_level_up, time_out=4, click_after_delay=0.5):
            self.mark_task_failure("找不到升级按钮")
            return False
        self.wait_click_feature(feature=fL.card_up_button, time_out=1, after_sleep=0.5)
        if not self.click_next(row=self.ScreenRow.MIDDLE):
            self.mark_task_failure("找不到下一步按钮")
            return False
        return True
