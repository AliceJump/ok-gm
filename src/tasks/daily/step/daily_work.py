from src.data.FeatureList import FeatureList as fL
from src.tasks.BaseGMTask import BaseGMTask
class DailyWork:
    def go_work(self):
        self.log_info("开始找小偶像干活...")
        if not self.wait_click_feature(feature=fL.work_enter, raise_if_not_found=False, click_after_delay=0.5):
            self.mark_task_failure("找不到干活的门")
            return False
        if self.click_ok(settle_time=1, time_out=8, click_after_delay=0.5, blind_point=(0.504, 0.042), after_sleep=4):
            self.click_ok(settle_time=1, time_out=4, click_after_delay=0.5, blind_point=(0.504, 0.042))
        self.wait_ui_stable(box=self.box_of_screen(0.044, 0.433, 0.943, 0.503))
        times = 0
        work_bool = False
        while self.wait_click_feature(feature=fL.work_select_enter, time_out=4, raise_if_not_found=False, click_after_delay=0.5, box=self.box_of_screen(0.226, 0.468, 0.769, 0.527)):
            self.log_info("找小偶像干活...")
            if not self.wait_click_feature(feature=fL.very_good_icon, time_out=6, box=self.box_of_screen(0.028, 0.556, 0.991, 0.804), raise_if_not_found=False, click_after_delay=0.5):
                self.log_info("未找到特爽角色，不干了")
            for i in range(2):
                if self.wait_click_feature(feature=fL.next_step, raise_if_not_found=False, click_after_delay=0.5):
                    self.log_info(f"第{i+1}次点击下一步")
                if i==0:
                    self.click_ok(settle_time=1, time_out=2, click_after_delay=0.5)
            if not self.click_ok(settle_time=1, time_out=4, click_after_delay=0.5):
                self.mark_task_failure("未找到开干小口，不干了")
                return False
            times += 1
            if times >= 2:
                self.log_info("干了两轮了，不可能干了")
                return True
            if not self.wait_feature(feature=fL.work_page_icon, time_out=4, settle_time=1, raise_if_not_found=False):
                self.mark_task_failure("超时未能回到干活界面")
                return False
            work_bool = True
        if not work_bool:
            self.log_info("没有找到小偶像干活的入口，可能是干活的冷却没到")
            self.all_ok = False
            self.unfinished_count = getattr(self, "unfinished_count", 0) + 1
        self.log_info("干完了!")
        return True