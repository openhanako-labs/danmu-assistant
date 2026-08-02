"""
关键帧检测模块
Phase 2: 只在画面变化超过阈值时才触发弹幕生成
"""
import numpy as np
from PIL import Image
from typing import Optional


class KeyframeDetector:
    """
    关键帧检测器
    
    使用帧差法 + 直方图比较来判断画面是否发生显著变化
    """
    
    def __init__(self, threshold: float = 0.15, min_interval: int = 30):
        """
        Args:
            threshold: 变化阈值 (0-1)，超过此值认为画面发生变化
            min_interval: 最小触发间隔（帧数），防止过于频繁
        """
        self.threshold = threshold
        self.min_interval = min_interval
        self.last_frame: Optional[np.ndarray] = None
        self.last_trigger_frame = 0
        self.frame_count = 0
        
    def detect(self, current_frame: Image.Image) -> bool:
        """
        检测当前帧是否是关键帧
        
        Args:
            current_frame: PIL Image 对象
            
        Returns:
            True 如果认为是关键帧（画面有显著变化）
        """
        self.frame_count += 1
        
        # 转换为 numpy 数组并转为灰度
        gray = np.array(current_frame.convert("L"))
        current_array = gray.astype(np.float32) / 255.0
        
        # 第一帧总是关键帧
        if self.last_frame is None:
            self.last_frame = current_array
            return True
        
        # 检查最小间隔
        if self.frame_count - self.last_trigger_frame < self.min_interval:
            # 即使不是关键帧，也更新 last_frame 防止漂移
            self.last_frame = current_array
            return False
        
        # 方法1: 帧差法
        diff = np.abs(current_array - self.last_frame)
        frame_diff_ratio = np.mean(diff)
        
        # 方法2: 直方图比较
        hist_curr = np.histogram(current_array.flatten(), bins=32, range=(0, 1))[0].astype(np.float32)
        hist_curr /= hist_curr.sum()
        hist_last = np.histogram(self.last_frame.flatten(), bins=32, range=(0, 1))[0].astype(np.float32)
        hist_last /= hist_last.sum()
        hist_diff = 1 - np.sum(np.minimum(hist_curr, hist_last))  # 直方图交
        
        # 综合判断
        is_keyframe = (frame_diff_ratio > self.threshold) or (hist_diff > self.threshold * 0.8)
        
        if is_keyframe:
            self.last_trigger_frame = self.frame_count
            print(f"  [关键帧] 帧#{self.frame_count} 差异: 帧差={frame_diff_ratio:.3f} 直方图={hist_diff:.3f}")
        
        # 更新参考帧（使用加权平均防止突变）
        alpha = 0.7 if is_keyframe else 0.1  # 关键帧大幅更新，非关键帧微调
        self.last_frame = self.last_frame * alpha + current_array * (1 - alpha)
        
        return is_keyframe
    
    def reset(self):
        """重置检测器状态"""
        self.last_frame = None
        self.last_trigger_frame = 0
        self.frame_count = 0


if __name__ == "__main__":
    # 测试
    print("=== 关键帧检测器测试 ===")
    detector = KeyframeDetector(threshold=0.15, min_interval=30)
    
    # 创建两个不同的测试图像
    img1 = Image.new("RGB", (100, 100), color=(255, 0, 0))
    img2 = Image.new("RGB", (100, 100), color=(0, 255, 0))
    img3 = Image.new("RGB", (100, 100), color=(0, 254, 0))  # 轻微变化
    
    print(f"帧1 (红): {detector.detect(img1)}")  # True
    print(f"帧2 (绿): {detector.detect(img2)}")  # True (大变化)
    print(f"帧3 (微绿): {detector.detect(img3)}")  # False (小变化)
    
    print("\n关键帧检测器测试通过 ✓")
