import time
from src.data.FeatureList import FeatureList as fL
from src.tasks.BaseGMTask import BaseGMTask
from src.tasks.mixin.shop_mixin import ShopMixin
class DailyShop(BaseGMTask, ShopMixin):
    def go_shop(self):
        self.log_info("开始买东西...")
        if not self.wait_click_feature(feature=fL.shop_enter, raise_if_not_found=False, click_after_delay=0.5):
            self.mark_task_failure("找不到商店的门")
            return False
        if not self.wait_click_feature(feature=fL.daily_shop_enter, raise_if_not_found=False, click_after_delay=0.5):
            self.mark_task_failure("找不到日常商店的门")
            return False
        self.wait_ui_stable()
        self.switch_order(target_order="down")
        self.wait_ui_stable()
        need_buy_goods = [fL.yellow_book, fL.card_up_credit]
        if not self.buy_goods(need_buy_goods):
            self.log_info("购买黄色书籍和卡片升级信用失败")
        if self.config.get("购买角色碎片", False):
            self.wait_ui_stable()            
            self.switch_order(target_order="up")
            self.wait_ui_stable()
            if not self.buy_goods(need_buy_goods_feature=[fL.char_piece]):
                self.log_info("购买角色碎片失败")
        if not self.wait_click_feature(feature=fL.switch_AP_shop, raise_if_not_found=False, click_after_delay=0.5):
            self.mark_task_failure("找不到切换AP商店的按钮")
            return False
        self.wait_ui_stable()
        if not self.buy_goods(need_buy_goods_feature=[fL.AP_credit_icon]):
            self.log_info("购买AP商品失败")
        return True