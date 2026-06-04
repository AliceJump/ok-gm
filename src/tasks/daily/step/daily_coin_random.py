import re
from src.data.FeatureList import FeatureList as fL

class DailyCoinRandom:
    def go_coin_random(self):
        if getattr(self, "pk_ok", False):
            self.log_info("配置里设置了pk_ok，跳过小偶像硬币抽奖")
            return True
        if not self.go_coin_page():
            return False
        self.wait_ui_stable()
        if not self.find_and_click_with_enough():
            self.mark_task_failure("没有找到满足条件的硬币，放弃点击。")
            return False
        if not self.change_cost():
            self.mark_task_failure("修改硬币消耗失败")
            return False
        if not self.click_ok():
            self.mark_task_failure("未找到确认按钮")
            return False
        if not self.click_close():
            self.mark_task_failure("未找到关闭按钮")
            return False
        self.log_info("完成了！")
        return True
    def go_coin_page(self):
        self.log_info("开始找小偶像硬币抽奖...")
        if not self.wait_click_feature(feature=fL.shop_enter, raise_if_not_found=False, click_after_delay=0.5):
            self.mark_task_failure("找不到小偶像硬币抽奖的门")
            return False
        if not self.wait_click_feature(feature=fL.coin_random_enter, raise_if_not_found=False, click_after_delay=0.5):
            self.mark_task_failure("找不到小偶像硬币抽奖的门")
            return False
        self.log_info("开干了!")
        return True
    def find_and_click_with_enough(self):
        for _ in range(2):
            results = self.find_feature(feature_name=fL.info_click, box=self.box_of_screen(0.876, 0.248, 0.935, 0.863))
            for result in results:
                num_area = self.box_of_screen(x=result.x/self.width-(0.878-0.376), y=result.y/self.height-(0.249-0.544), width=0.624-0.378, height=0.572-0.546)
                left_num = self.ocr(match=re.compile(r"\d+"), box=num_area)
                if left_num:
                    num = int(left_num[0].name)
                    self.log_info(f"找到一个硬币数：{num}")
                    if num > 10:
                        self.log_info("硬币数大于10，点击它！")
                        self.click(x=result.x/self.width-(0.878-0.376)+(0.496-0.383), y=result.y/self.height-(0.249-0.544)+(0.522-0.546))
                        return True
                    else:
                        self.log_info("硬币数不大于10，不点击它。")
                else:
                    self.log_info("未能识别数字")
            self.scroll_relative(0.5, 0.5, -16)
        self.log_info("没有找到满足条件的硬币，放弃点击。")
        return False
    def change_cost(self):
        subtraction = self.wait_feature(feature=fL.subtraction_button, time_out=4, raise_if_not_found=False, settle_time=1)
        if not subtraction:
            self.mark_task_failure("未找到减号按钮")
            return False
        self.click(subtraction.x+int((0.35-0.15)*self.width), subtraction.y+subtraction.height//2, after_sleep=0.5)
        if not self.wait_click_feature(feature=fL.add_button, time_out=4, raise_if_not_found=False, click_after_delay=0.5, after_sleep=0.5):
            self.mark_task_failure("未找到加号按钮")
            return False
        return True