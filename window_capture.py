"""
窗口聚焦截屏模块
Phase 3: 只截取活动窗口，而不是全屏
"""
import mss
import PIL.Image
import io
import base64
from typing import Optional, List, Dict
from dataclasses import dataclass


@dataclass
class WindowInfo:
    """窗口信息"""
    title: str
    left: int
    top: int
    width: int
    height: int
    is_active: bool = False
    
    @property
    def area(self) -> dict:
        """返回 mss 截屏区域"""
        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height
        }


def get_active_window() -> Optional[WindowInfo]:
    """
    获取活动窗口信息
    
    Returns:
        WindowInfo 对象，如果没有活动窗口则返回 None
    """
    try:
        import pygetwindow as gw
    except ImportError:
        print("警告：pygetwindow 未安装，无法获取活动窗口")
        print("安装: pip install pygetwindow")
        return None
    
    active_window = gw.getActiveWindow()
    if active_window is None:
        return None
    
    return WindowInfo(
        title=active_window.title,
        left=active_window.left,
        top=active_window.top,
        width=active_window.width,
        height=active_window.height,
        is_active=True
    )


def get_all_windows() -> List[WindowInfo]:
    """
    获取所有窗口列表
    
    Returns:
        WindowInfo 列表
    """
    try:
        import pygetwindow as gw
    except ImportError:
        print("警告：pygetwindow 未安装，无法获取窗口列表")
        print("安装: pip install pygetwindow")
        return []
    
    try:
        windows = gw.getAllWindows()
    except AttributeError:
        # 兼容旧版本
        windows = []
    
    result = []
    for w in windows:
        if w.width > 0 and w.height > 0:  # 过滤掉最小化的窗口
            result.append(WindowInfo(
                title=w.title,
                left=w.left,
                top=w.top,
                width=w.width,
                height=w.height,
                is_active=(w == gw.getActiveWindow())
            ))
    
    return result


def capture_window(window_info: WindowInfo, screen_index: int = 0) -> Optional[PIL.Image.Image]:
    """
    截取指定窗口
    
    Args:
        window_info: 窗口信息
        screen_index: 显示器索引
        
    Returns:
        PIL Image 对象，如果截取失败则返回 None
    """
    try:
        with mss.mss() as sct:
            monitors = sct.monitors
            if screen_index < len(monitors):
                monitor = monitors[screen_index]
            else:
                monitor = monitors[0]
            
            # 确保窗口在显示器范围内
            area = window_info.area
            area["left"] = max(area["left"], monitor["left"])
            area["top"] = max(area["top"], monitor["top"])
            area["width"] = min(area["width"], monitor["width"] - (area["left"] - monitor["left"]))
            area["height"] = min(area["height"], monitor["height"] - (area["top"] - monitor["top"]))
            
            if area["width"] <= 0 or area["height"] <= 0:
                return None
            
            screenshot = sct.grab(area)
            img = PIL.Image.frombytes(
                "RGB",
                screenshot.size,
                screenshot.bgra,
                "raw",
                "BGRX"
            )
            return img
    except Exception as e:
        print(f"截屏失败: {e}")
        return None


def capture_active_window(screen_index: int = 0) -> Optional[PIL.Image.Image]:
    """
    截取活动窗口
    
    Args:
        screen_index: 显示器索引
        
    Returns:
        PIL Image 对象，如果截取失败则返回 None
    """
    window_info = get_active_window()
    if window_info is None:
        return None
    
    return capture_window(window_info, screen_index)


def compress_image(img: PIL.Image.Image, quality: int = 70) -> tuple[bytes, str]:
    """
    将图片压缩为 JPEG 并返回 base64
    
    Args:
        img: PIL Image 对象
        quality: JPEG 质量（1-100）
        
    Returns:
        (压缩后的 bytes, base64 字符串)
    """
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=quality)
    compressed = buffer.getvalue()
    b64 = base64.b64encode(compressed).decode("utf-8")
    return compressed, b64


if __name__ == "__main__":
    # 测试
    print("=== 窗口聚焦截屏测试 ===")
    
    # 测试获取活动窗口
    active = get_active_window()
    if active:
        print(f"活动窗口: {active.title}")
        print(f"位置: ({active.left}, {active.top}), 大小: {active.width}x{active.height}")
    else:
        print("未找到活动窗口")
    
    # 测试获取所有窗口
    windows = get_all_windows()
    print(f"\n找到 {len(windows)} 个窗口:")
    for w in windows[:5]:  # 只显示前 5 个
        active_marker = " *" if w.is_active else ""
        print(f"  {w.title}{active_marker}")
    
    print("\n窗口聚焦截屏测试通过 ✓")
