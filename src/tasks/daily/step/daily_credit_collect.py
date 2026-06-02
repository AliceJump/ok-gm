from src.data.FeatureList import FeatureList as fL
from src.tasks.BaseGMTask import BaseGMTask
class DailyCreditCollect:
    def go_credit_collect(self):
        self.log_info("开始收米...")
        if not self.wait_click_feature(feature=fL.credit_enter, raise_if_not_found=False, click_after_delay=0.5):
            self.mark_task_failure("找不到收米的地方")
            return False
        if not self.wait_click_feature(feature=fL.close_button, raise_if_not_found=False, click_after_delay=0.5):
            self.mark_task_failure("找不到关闭按钮")
            return False
        self.log_info("收完了!")
        return True