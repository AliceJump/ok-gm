from src.data.FeatureList import FeatureList as fL
from src.tasks.BaseGMTask import BaseGMTask
class DailyCreditCollect(BaseGMTask):
    def go_credit_collect(self):
        self.log_info("开始收米...")
        if not self.click_feature(feature_name=fL.credit_enter, click_after_delay=0.5):
            self.mark_task_failure("找不到收米的地方")
            return False
        if not self.click_close():
            self.mark_task_failure("找不到关闭按钮")
            return False
        self.log_info("收完了!")
        return True
