from src.tasks.BaseGMTask import BaseGMTask
from src.data.FeatureList import FeatureList as fL
class DailyGift(BaseGMTask):
    def go_gift(self):
        self.log_info("开始收小礼物...")
        if not self.click_feature(feature_name=fL.gift_enter, click_after_delay=0.5):
            self.mark_task_failure("找不到小礼物的门")
            return False
        if not self.click_next(row=self.ScreenRow.TOP, verify_disappear=False):
            self.log_info("没有下一步了，可能小礼物已经领完了")
        else:
            self.click_close(time_out=2)
        return True
