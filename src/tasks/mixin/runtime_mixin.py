
import cv2
import imagehash
import time
from PIL import Image
from ok import Box
import numpy as np
from src.image.frame_processes import isolate_by_hsv_ranges
from skimage.metrics import structural_similarity as ssim
class RuntimeMixin:
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
                    return frame[y:y + h, x:x + w]

                if isinstance(box, (tuple, list)) and len(box) == 4:
                    x, y, w, h = map(int, box)
                    return frame[y:y + h, x:x + w]

                raise ValueError("box must be None / (x,y,w,h) / object(x,y,width,height)")

            start_time = time.time()
            last_frame = parse_box(self.next_frame(), box)
            stable_start = None

            while True:
                current_frame = parse_box(self.next_frame(), box)

                if method in ("phash", "dhash"):
                    img1 = Image.fromarray(last_frame)
                    img2 = Image.fromarray(current_frame)

                    h1 = imagehash.phash(img1) if method == "phash" else imagehash.dhash(img1)
                    h2 = imagehash.phash(img2) if method == "phash" else imagehash.dhash(img2)

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
    def wait_until_feature(self, target_feature, action_feature, box=None,
                        timeout=60, click_delay=0.5, loop_sleep=0.8,
                        allow_unrecognized_click=False,
                        block_until_action=True,
                        skip_target_check_after_action=False):
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
                self.mark_task_failure(f"等待 {target_feature} 超时 (已等待 {elapsed:.1f}s)")
                return False

            # ==================== 1. 处理 Action ====================
            clicked = self.wait_click_feature(
                feature=action_feature,
                raise_if_not_found=False,
                click_after_delay=click_delay,
                time_out=1
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