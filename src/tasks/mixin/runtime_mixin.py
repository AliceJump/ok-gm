from datetime import datetime

import cv2
import imagehash
import time
from PIL import Image
from ok import Box
from enum import Enum
import numpy as np
import pyautogui
from src.image.frame_processes import isolate_by_hsv_ranges
from skimage.metrics import structural_similarity as ssim
from src.interaction.Mouse import (
    run_at_window_pos,
    active_and_send_mouse_delta as send_mouse_delta,
)
from src.data.FeatureList import FeatureList as fL


class ScreenRow(Enum):
    """
    定义屏幕行枚举，表示界面上不同垂直位置的区域划分。
    """
    TOP = "top"
    MIDDLE = "middle"
    BOTTOM = "bottom"


BUTTON_ROW_Y = {
    ScreenRow.TOP: (0.814, 0.880),
    ScreenRow.MIDDLE: (0.880, 0.930),
    ScreenRow.BOTTOM: (0.929, 0.969),
}

BUTTON_COL_X = [
    (0.140, 0.220),
    (0.337, 0.413),
    (0.540, 0.613),
]


class RuntimeMixin:
    @property
    def button_boxs(self):
        return self.get_button_boxs()

    def get_button_boxs(self, row=ScreenRow.MIDDLE):
        y1, y2 = BUTTON_ROW_Y[row]

        return [self.box_of_screen(x1, y1, x2, y2) for x1, x2 in BUTTON_COL_X]
    

    def wait_ui_stable(
        self,
        method="phash",
        threshold: int = 5,
        stable_time: float = 0.5,
        max_wait: float = 5,
        refresh_interval: float = 0.2,
        box: Box | tuple | list | None = None,
    ):
        """
        等待指定区域在视觉上稳定下来。

        Args:
            method: 稳定性判断方法。
            threshold: 稳定阈值。
            stable_time: 持续稳定时长。
            max_wait: 最长等待时间。
            refresh_interval: 帧刷新间隔。
            box: 需要监测的区域。

        Returns:
            bool: 稳定后返回 True，超时返回 False。

        Raises:
            ValueError: 当 method 不支持或 box 非法时抛出。
        """

        def parse_box(frame, box: Box | tuple | list | None):
            if box is None:
                return frame

            if hasattr(box, "x"):
                x = int(box.x)
                y = int(box.y)
                w = int(box.width)
                h = int(box.height)
                return frame[y : y + h, x : x + w]

            if isinstance(box, (tuple, list)) and len(box) == 4:
                x, y, w, h = map(int, box)
                return frame[y : y + h, x : x + w]

            raise ValueError("box must be None / (x,y,w,h) / object(x,y,width,height)")

        start_time = time.time()
        last_frame = parse_box(self.next_frame(), box)
        stable_start = None

        while True:
            current_frame = parse_box(self.next_frame(), box)

            if method in ("phash", "dhash"):
                img1 = Image.fromarray(last_frame)
                img2 = Image.fromarray(current_frame)

                h1 = (
                    imagehash.phash(img1)
                    if method == "phash"
                    else imagehash.dhash(img1)
                )
                h2 = (
                    imagehash.phash(img2)
                    if method == "phash"
                    else imagehash.dhash(img2)
                )

                is_stable = (h1 - h2) <= threshold

            elif method == "pixel":
                if last_frame.shape != current_frame.shape:
                    is_stable = False
                else:
                    diff = cv2.absdiff(last_frame, current_frame)
                    is_stable = np.mean(diff) <= threshold

            elif method == "ssim":
                last_gray = cv2.cvtColor(last_frame, cv2.COLOR_BGR2GRAY)
                current_gray = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)

                if last_gray.shape != current_gray.shape:
                    is_stable = False
                else:
                    score, _ = ssim(last_gray, current_gray, full=True)
                    is_stable = score >= threshold

            else:
                raise ValueError(f"Unknown method {method}")

            if is_stable:
                if stable_start is None:
                    stable_start = time.time()
                elif time.time() - stable_start >= stable_time:
                    return True
            else:
                stable_start = None

            if time.time() - start_time > max_wait:
                return False

            last_frame = current_frame
            self.sleep(refresh_interval)

    def make_hsv_isolator(self, ranges):
        """返回一个可直接调用的 HSV 过滤函数"""
        return lambda frame, invert=True, kernel_size=2: isolate_by_hsv_ranges(
            frame, ranges, invert=invert, kernel_size=kernel_size
        )

    def wait_until_feature(
        self,
        target_feature,
        action_feature,
        box=None,
        timeout=60,
        click_delay=0.5,
        loop_sleep=0.8,
        allow_unrecognized_click=False,
        block_until_action=True,
        skip_target_check_after_action=False,
    ):
        """等待点击 action_feature 后，target_feature 出现。

        先尝试点击指定的 action_feature（操作特征），然后等待 target_feature（目标特征）
        出现，常用于界面跳转、按钮点击后新页面加载的场景。

        Args:
            target_feature (str): 目标特征名称（最终要等待出现的界面/按钮特征）。
            action_feature (str): 操作特征名称（需要先点击的按钮/特征）。
            box (Box | tuple | list | None): 限制特征识别的区域，None 表示全屏。
            timeout (float): 最大等待时间（秒）。超时会调用 mark_task_failure。
            click_delay (float): 点击 action 后的延迟时间（秒）。
            loop_sleep (float): 每轮循环的睡眠时间（秒）。
            allow_unrecognized_click (bool): 当 action_feature 未找到时，是否执行备用点击。
            block_until_action (bool): 是否必须成功点击过 action 后才开始检测 target。
                - True（默认）：必须先点击成功才检测 target（推荐）。
                - False：每轮都检测 target。
            skip_target_check_after_action (bool): 成功点击 action 后，本轮是否跳过 target 检测。
                - True：点击成功后直接 continue（给界面加载时间）。
                - False（默认）：点击成功后立即检测 target。

        Returns:
            bool: 成功找到 target_feature 返回 True，超时返回 False。

        Raises:
            无异常抛出，但超时会调用 self.mark_task_failure。
        """
        start_time = time.time()
        action_triggered = False

        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                self.mark_task_failure(
                    f"等待 {target_feature} 超时 (已等待 {elapsed:.1f}s)"
                )
                return False

            # ==================== 1. 处理 Action ====================
            clicked = self.wait_click_feature(
                feature=action_feature,
                raise_if_not_found=False,
                click_after_delay=click_delay,
                time_out=1,
            )

            if clicked:
                action_triggered = True
                self.log_info(f"已触发 action: {action_feature}")

                # 如果设置了跳过本轮target检测，则直接进入下一次循环
                if skip_target_check_after_action:
                    self.sleep(loop_sleep)
                    continue

            elif allow_unrecognized_click:
                self.click(0.865, 0.916)
                self.log_info(f"执行未识别点击 fallback")

            # ==================== 2. 检查 Target ====================
            if not block_until_action or action_triggered:
                if self.find_feature(feature_name=target_feature, box=box):
                    self.log_info(f"成功找到目标: {target_feature}")
                    return True

            self.sleep(loop_sleep)

    def scroll(self, x: int, y: int, count: int) -> None:
        """按屏幕绝对像素坐标滚轮。

        Args:
            x: 滚动位置的绝对像素 X 坐标
            y: 滚动位置的绝对像素 Y 坐标
            count: 滚动量。
                正数（向上滚动）：地图 UI 放大视角 / 列表 UI 向上翻页显示靠前内容。
                负数（向下滚动）：地图 UI 缩小视角或向下平移 / 列表 UI 向下翻页显示靠后内容。

        适用场景：
        - 地图 UI：已确定地图中心/图标附近的像素坐标时，精确缩放或平移视角。
        - 列表 UI：已通过 OCR/特征拿到某一行条目的绝对坐标时，在该条目处滚动翻页。
        """
        run_at_window_pos(self.hwnd.hwnd, self.do_scroll, x, y, 0.5, count)

    def scroll_relative(self, x: float, y: float, count: int) -> None:
        """按屏幕相对坐标比例滚轮（x/y 范围 0~1）。

        Args:
            x: 滚动位置的相对 X 坐标（0~1，0 为左边缘，1 为右边缘）
            y: 滚动位置的相对 Y 坐标（0~1，0 为上边缘，1 为下边缘）
            count: 滚动量。
                正数（向上滚动）：地图 UI 放大视角 / 列表 UI 向上翻页显示靠前内容。
                负数（向下滚动）：地图 UI 缩小视角或向下平移 / 列表 UI 向下翻页显示靠后内容。

        适用场景：
        - 地图 UI：用 (0.5, 0.5) 等比例坐标在地图中心连续缩放，适配不同分辨率。
        - 列表 UI：在固定相对区域（如左侧列表 0.1/0.5）滚动查找条目，避免硬编码像素。
        """
        run_at_window_pos(
            self.hwnd.hwnd,
            self.do_scroll,
            int(x * self.width),
            int(y * self.height),
            0.5,
            count,
        )

    def do_scroll(self, times):
        direction = 1 if times >= 0 else -1
        self.active_and_send_mouse_delta(activate=True, only_activate=True)
        for _ in range(abs(times)):
            pyautogui.scroll(direction)
            self.sleep(0.1)

    def active_and_send_mouse_delta(
        self, dx=1, dy=1, activate=True, only_activate=False, delay=0.02, steps=3
    ):
        """
        激活窗口后发送鼠标位移。

        Args:
            dx: 水平位移。
            dy: 垂直位移。
            activate: 是否激活窗口。
            only_activate: 是否只激活不移动。
            delay: 步进间隔延迟。
            steps: 步进次数。

        Returns:
            Any: send_mouse_delta 的返回值。
        """
        return send_mouse_delta(
            self.hwnd.hwnd, dx, dy, activate, only_activate, delay, steps
        )

    def ensure_main(self, esc=True, time_out=60, after_sleep=2, need_active=True):
        """
        确保回到主界面（游戏世界）。

        Args:
            esc: 是否在失败时执行返回键处理。
            time_out: 等待主界面的总超时时间。
            after_sleep: 成功后额外等待时间。
            need_active: 是否先激活窗口。

        Returns:
            None

        Raises:
            Exception: 当无法回到主界面时抛出。
        """
        self.info_set("current task", f"wait main esc={esc}")
        if not self.wait_until(
            lambda: self.is_main(esc=esc, need_active=need_active),
            time_out=time_out,
            raise_if_not_found=False,
        ):
            raise Exception("Please start in game world and in team!")
        self.sleep(after_sleep)
        self.info_set("current task", f"in main esc={esc}")

    def wait_login(self):
        """
        处理登录界面的各种弹窗（月卡、签到、奖励等）。

        Returns:
            bool: 已进入主界面或已成功处理登录弹窗时返回 True，否则返回 False。
        """
        close = None
        if not self._logged_in:
            if self.in_main() or self.find_one(
                feature_name=[fL.back, fL.process_back_home, fL.hall_back_home]
            ):
                self._logged_in = True
                return True
            elif self.find_one(fL.login_click):
                run_at_window_pos(
                    self.hwnd.hwnd,
                    super().click,
                    self.width // 2,
                    self.height // 2,
                    1,
                    0.5,
                    0.5,
                )
                return False
            elif close := (
                self.find_one(
                    fL.reward_sign_in,
                    horizontal_variance=0.3,
                    vertical_variance=0.1,
                )
            ):
                if close.name == fL.reward_sign_in:
                    close.y += int(self.height // 10)
                self.click(close, after_sleep=1)
                return False
            elif self.click_ok(time_out=1, after_sleep=0):
                return False
            self.click(0.502, 0.958)
        return False

    def is_main(self, esc=False, need_active=True):
        """
        判断是否处于可执行任务的主界面状态。

        Args:
            esc: 是否在处理失败时按返回键。
            need_active: 是否需要先激活窗口。

        Returns:
            bool: 处于主界面返回 True，否则返回 False。
        """

        self.next_frame()

        if not self._logged_in and need_active:
            self.active_and_send_mouse_delta(activate=True, only_activate=True)

        # 已进入世界
        if self.wait_until(self.in_main, time_out=1):
            self._logged_in = True
            return True

        # 登录流程处理成功
        if self.wait_login():
            return True

        # # 命中 OCR 干扰并进行了处理，当前不视为稳定主界面
        # rules = [[
        #     None,
        #     None,
        #     [self.lang.game_flow_mixin.k_8b2ca27a, self.lang.game_flow_mixin.k_7cd2e0c0],
        #     self.box.bottom
        # ]]

        # if self.handle_ocr_rules(rules):
        #     return False

        if esc:
            # self.back(after_sleep=1.5)
            self.wait_click_feature(
                feature=[
                    fL.close_button,
                    fL.align_close_button,
                    fL.skip_dialog,
                    fL.process_back_home,
                    fL.hall_back_home,
                    fL.back,
                ],
                time_out=2,
                raise_if_not_found=False,
                click_after_delay=0.5,
                horizontal_variance=0.1,
                vertical_variance=0.1,
            )

    def in_main(self):
        """
        判断是否在游戏世界中（非菜单/对话状态）。

        Returns:
            bool: 当前处于游戏世界返回 True。
        """
        main_world_features = [fL.gift_enter]

        in_world = all(
            self.find_one(f, vertical_variance=0.01, horizontal_variance=0.02)
            for f in main_world_features
        )

        if in_world:
            self._logged_in = True

        return in_world

    def feature_stable(self, feature_name, box, duration):
        if duration <= 0:
            return True

        end_time = time.time() + duration
        while time.time() < end_time:
            if not self.find_feature(
                feature_name=feature_name, box=box, frame=self.next_frame()
            ):
                return False
            self.sleep(0.05)

        return True

    def click_feature(
        self,
        feature_name,
        boxes=None,
        time_out=5,
        after_sleep=0,
        click_after_delay=0,
        settle_time=0,
        blind_point=None,
        blind_delay=1,
        verify_disappear=True,
        verify_timeout=0.5,
        max_click_retry=3
    ):
        boxes = [None] + (boxes or [])

        start_time = time.time()
        last_blind_time = 0

        while time.time() - start_time < time_out:
            frame = self.next_frame()

            for box in boxes:
                result = self.find_feature(
                    feature_name=feature_name,
                    box=box,
                    frame=frame,
                )

                if result and self.feature_stable(feature_name, box, settle_time):
                    retry_count = 0

                    while retry_count < max_click_retry:
                        self.sleep(click_after_delay)

                        self.click(result, after_sleep=after_sleep)

                        if not verify_disappear:
                            return True

                        if self.wait_feature_disappear(
                            feature_name,
                            box,
                            verify_timeout,
                        ):
                            return True

                        self.log_warning(
                            f"{feature_name} 点击后未消失，重试 {retry_count + 1}/{max_click_retry}"
                        )

                        retry_count += 1

            if blind_point and (time.time() - last_blind_time >= blind_delay):
                self.click(
                    blind_point[0],
                    blind_point[1],
                    after_sleep=after_sleep,
                )
                last_blind_time = time.time()

        return False
    
    def wait_feature_disappear(
        self,
        feature_name,
        box=None,
        timeout=1,
    ):
        start = time.time()

        while time.time() - start < timeout:
            frame = self.next_frame()

            if not self.find_feature(
                feature_name=feature_name,
                box=box,
                frame=frame,
            ):
                return True

        return False
    
    def click_ok(
        self,
        row=ScreenRow.MIDDLE,
        time_out=5,
        after_sleep=0,
        blind_point=None,
        blind_delay=0,
        click_after_delay=0.5,
        verify_disappear=True,
        verify_timeout=0.5,
        max_click_retry=3
    ):
        return self.click_feature(
            feature_name=fL.ok_button,
            boxes=self.get_button_boxs(row=row),
            time_out=time_out,
            after_sleep=after_sleep,
            blind_point=blind_point,
            blind_delay=blind_delay,
            click_after_delay=click_after_delay,
            verify_disappear=verify_disappear,
            verify_timeout=verify_timeout,
            max_click_retry=max_click_retry
        )

    def click_close(
        self,
        row=ScreenRow.MIDDLE,
        time_out=5,
        after_sleep=0,
        blind_point=None,
        blind_delay=0,
        click_after_delay=0.5,
        verify_disappear=True,
        verify_timeout=0.5,
        max_click_retry=3,
    ):
        return self.click_feature(
            feature_name=[fL.close_button, fL.align_close_button],
            boxes=self.get_button_boxs(row=row),
            time_out=time_out,
            after_sleep=after_sleep,
            blind_point=blind_point,
            blind_delay=blind_delay,
            click_after_delay=click_after_delay,
            verify_disappear=verify_disappear,
            verify_timeout=verify_timeout,
            max_click_retry=max_click_retry
        )

    def click_next(
        self,
        row=ScreenRow.MIDDLE,
        time_out=5,
        after_sleep=0,
        blind_point=None,
        blind_delay=0,
        click_after_delay=0.5,
        verify_disappear=True,
        verify_timeout=0.5,
        max_click_retry=3
    ):
        return self.click_feature(
            feature_name=fL.next_step,
            boxes=self.get_button_boxs(row=row),
            time_out=time_out,
            after_sleep=after_sleep,
            blind_point=blind_point,
            blind_delay=blind_delay,
            click_after_delay=click_after_delay,
            verify_disappear=verify_disappear,
            verify_timeout=verify_timeout,
            max_click_retry=max_click_retry
        )

    def get_order_status(self, time_out=5):
        boxes = [self.box_of_screen(0.746, 0.767, 0.787, 0.790), self.box_of_screen(0.885, 0.767, 0.935, 0.790)]
        features = [fL.down_order_button, fL.up_order_button_dark, fL.up_order_button, fL.down_order_button_dark]
        

        start_time = time.time()

        while time.time() - start_time < time_out:
            for feature in features:
                for box in boxes:
                    if result := self.find_feature(feature_name=feature, box=box, threshold=0.7):
                        return result, (
                            "down" if fL.down_order_button in feature else "up"
                        )

            self.sleep(0.05)

        return None, None

    def switch_order(self, target_order="up"):
        switch_order, status = self.get_order_status()
        if not status:
            self.log_info("无法获取当前排序状态，无法切换")
            return False
        current_order = status
        if current_order == target_order:
            self.log_info(f"当前已经是{target_order}序了，无需切换")
            return True
        else:
            self.click(switch_order, after_sleep=1)
            _, new_status = self.get_order_status()
            if new_status and new_status == target_order:
                self.log_info(f"成功切换到{target_order}序")
                return True
            else:
                self.log_info(f"切换排序失败，当前仍然是{current_order}序")
                return False
