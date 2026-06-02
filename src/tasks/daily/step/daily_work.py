from src.data.FeatureList import FeatureList as fL
from src.tasks.BaseGMTask import BaseGMTask
class DailyWork:
    def go_work(self):
        self.log_info("开始找小偶像干活...")
        if not self.wait_click_feature(feature=fL.work_enter, raise_if_not_found=False, click_after_delay=0.5):
            self.mark_task_failure("找不到干活的门")
            return False
        self.wait_ui_stable(box=self.box_of_screen(0.044, 0.433, 0.943, 0.503))
        work_select_enters=self.find_feature(feature_name=fL.work_select_enter, box=self.box_of_screen(0.226, 0.468, 0.769, 0.527))

        if not work_select_enters:
            self.mark_task_failure("选不到小偶像")
            return False
        
        for work_select_enter in work_select_enters:
            self.click(work_select_enter)
            self.log_info("找小偶像干活...")
            if not self.wait_click_feature(feature=fL.very_good_icon, raise_if_not_found=False, click_after_delay=0.5):
                self.mark_task_failure("未找到特爽角色，不干了")
                return False
            for i in range(2):
                if self.wait_click_feature(feature=fL.next_step, raise_if_not_found=False, click_after_delay=0.5):
                    self.log_info(f"第{i+1}次点击下一步")
                if i==0:
                    self.wait_click_feature(feature=fL.ok_button, time_out=2, raise_if_not_found=False, click_after_delay=0.5, box=self.box_of_screen(0.544, 0.892, 0.602, 0.919))
            if not self.wait_click_feature(feature=fL.ok_button, raise_if_not_found=False, click_after_delay=0.5, box=self.box_of_screen(0.544, 0.892, 0.602, 0.919)):
                self.mark_task_failure("未找到开干小口，不干了")
                return False
        self.log_info("干完了!")
        return True