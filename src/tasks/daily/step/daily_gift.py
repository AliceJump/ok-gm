from src.tasks.BaseGMTask import BaseGMTask
from src.data.FeatureList import FeatureList as fL
class DailyGift:
    def go_gift(self):
        self.log_info("开始收小礼物...")
        if not self.wait_click_feature(feature=fL.gift_enter, raise_if_not_found=False, click_after_delay=0.5):
            self.mark_task_failure("找不到小礼物的门")
            return False
        if not self.wait_click_feature(feature=fL.next_step, raise_if_not_found=False, click_after_delay=0.5, box=self.box_of_screen(0.344, 0.832, 0.404, 0.863)):
            self.log_info("没有下一步了，可能小礼物已经领完了")
        else:
            self.click_close(time_out=2)
        return True