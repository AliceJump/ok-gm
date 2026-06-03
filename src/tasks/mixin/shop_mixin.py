class ShopMixin:
    
    def buy_goods(self, need_buy_goods=None, need_buy_goods_feature=None):
        if need_buy_goods is None:
            need_buy_goods = []
        goods_area = self.box_of_screen(0.026, 0.242, 0.978, 0.760)
        goods = []

        for feature in need_buy_goods:
            good = self.wait_feature(
                feature=feature,
                box=goods_area,
                time_out=4,
                raise_if_not_found=False
            )

            if not good:
                self.log_info(f"找不到{feature}")
                continue

            goods.append(good)

        goods.extend(
            self.find_feature(
                feature_name=need_buy_goods_feature,
                box=goods_area,
                threshold=0.9
            ) if need_buy_goods_feature else []
        )

        for good in goods:
            if not self.click(good, after_sleep=0.5):
                self.log_info(f"点击{good}失败")
                continue

            if not self.click_ok(after_sleep=0.5):
                self.mark_task_failure(f"找不到{good}的购买确认按钮")
        return True