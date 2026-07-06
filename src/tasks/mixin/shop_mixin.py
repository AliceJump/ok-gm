class ShopMixin:
    
    def buy_goods(self, need_buy_goods=None, need_buy_goods_feature=None, retry_times=1):
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
            retry_time = retry_times
            while retry_time > 0:
                self.click(good)
                if self.click_ok(after_sleep=1, time_out=2):
                    break
                self.click_close(time_out=1, after_sleep=0.5)
                retry_time -= 1
            if retry_time == 0:
                self.mark_task_failure(f"购买{good}失败")
        return True