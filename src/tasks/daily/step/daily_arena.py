import time
import re
from src.data.FeatureList import FeatureList as fL
from src.tasks.BaseGMTask import BaseGMTask
class DailyArena(BaseGMTask):
    def go_arena(self):
        if not self.enter_arena():
            return False
        if not self.check_arena_pop_up():
            self.mark_task_failure("竞技场结算界面异常")
            return False
        pk_times, total_times = self.get_arena_ticket_number()
        if total_times == 0:
            self.mark_task_failure("竞技场系统异常，找不到竞技场票的OCR结果")
            return False
        if pk_times == 0:
            self.log_info("没有竞技场票了")
            return True
        for _ in range(pk_times):
            if not self.pk_arena():
                return False
        return True
    def enter_arena(self):
        self.log_info("开始打小偶像竞技场...")
        if not self.wait_click_feature(feature=fL.switch_arena_page, raise_if_not_found=False, click_after_delay=0.5):
            self.mark_task_failure("找不到切换到竞技场的按钮")
            return False
        if not self.wait_click_feature(feature=fL.arena_enter, raise_if_not_found=False, click_after_delay=0.5):
            self.mark_task_failure("找不到进入竞技场的按钮")
            return False
        self.log_info("开干了!")
        return True
    def check_arena_pop_up(self):
        if self.wait_click_feature(feature=fL.arena_checkout, settle_time=1, time_out=4, raise_if_not_found=False, click_after_delay=0.5):
            self.log_info("竞技场结算界面弹出来了，可能是上次竞技场结算")
            if result:= self.wait_feature(feature=fL.arena_star_checkout, raise_if_not_found=False):
                self.click(result.x, result.y+0.2*self.height)
                return True
            else:
                self.mark_task_failure("找不到梅开二度")
                return False
        else:
            return True
    def pk_arena(self):
        if not self.wait_click_feature(feature=fL.first_opponent, raise_if_not_found=False, click_after_delay=0.5):
            self.mark_task_failure("找不到第一个对手")
            return False
        self.log_info("开干了!")
        if not self.wait_click_feature(feature=fL.start_pk, raise_if_not_found=False, click_after_delay=0.5):
            self.mark_task_failure("找不到开始的按钮")
            return False
        if not self.wait_click_feature(feature=fL.skip_pk, raise_if_not_found=False, click_after_delay=0.5, time_out=30):
            self.mark_task_failure("找不到跳过按钮，可能是卡死了")
            return False
        
        self.wait_until_feature(fL.arena_no_1, fL.skip_pk, box=self.box_of_screen(0.059, 0.241, 0.935, 0.275), allow_unrecognized_click=True, skip_target_check_after_action=True)

        for i in range(2):
            if not self.click_next(row=self.ScreenRow.MIDDLE):
                self.mark_task_failure("找不到下一步按钮")
                return False
        if not self.click_close(time_out=4):
            self.log_info("找不到关闭按钮,可能本次没有显式奖励")
        return True
    def get_arena_ticket_number(self):
        result = self.wait_ocr(match=re.compile(r'\d+/\d+'), time_out=5, box=self.box_of_screen(0.780, 0.013, 0.904, 0.051))
        
        if result:
            text = result[0].name
            if '/' in text:
                current, total = text.split('/')
                try:
                    current = int(current)
                    total = int(total)
                    self.all_ok = True
                    return current, total
                except ValueError:
                    self.mark_task_failure(f"竞技场票OCR结果解析失败: {text}")
                    self.all_ok = False
                    self.unfinished_count = getattr(self, "unfinished_count", 0) + 1
                    return 0, 0
        self.mark_task_failure("未找到竞技场票OCR结果")
        self.all_ok = False
        self.unfinished_count = getattr(self, "unfinished_count", 0) + 1
        return 0, 0
