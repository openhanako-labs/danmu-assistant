"""
弹幕浮层 - 全屏透明版
覆盖整个屏幕，鼠标穿透，不影响游戏操作
"""
import sys
import time
import threading
import ctypes
from dataclasses import dataclass, field
from typing import Optional
from collections import deque

from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter


class DanmuEngine:
    def __init__(self, width: int = 3840, height: int = 1080, tracks: int = 8):
        self.width = width
        self.height = height
        self.tracks = tracks
        self.track_height = height // tracks
        self.queue: deque = deque()
        self.running = True

    def add_danmu(self, content: str, color: str = "#ffffff", track: int = 0):
        # 速度 3~6 px/frame，随机差异更大
        speed = 3.0 + abs(hash(content + str(time.time()))) % 4
        self.queue.append({
            "text": content, "color": color,
            "speed": speed, "track": track % self.tracks
        })

    def drain(self) -> list:
        items = []
        while self.queue:
            items.append(self.queue.popleft())
        return items


@dataclass
class RenderItem:
    text: str = ""
    color: str = "#ffffff"
    speed: float = 3.0
    track: int = 0
    x: float = 0.0
    width: float = 0.0
    visible: bool = True


class DanmuOverlay(QWidget):
    """全屏透明弹幕浮层。"""

    def __init__(self, engine: DanmuEngine):
        super().__init__()
        self.engine = engine
        self.items: list[RenderItem] = []
        self.font = QFont("Microsoft YaHei", 20, QFont.Weight.Bold)
        self.font_metrics = QFontMetrics(self.font)
        self._track_last_emit: dict = {}  # track -> last emit timestamp

        # 窗口设置：全屏、无边框、置顶、工具窗口
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        # 完全透明背景
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        # 鼠标穿透
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        # 样式透明
        self.setStyleSheet("background: transparent;")

        # 定时器：30fps 足够弹幕使用
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)  # ~30fps

    def show_fullscreen(self):
        """铺满所有屏幕。"""
        # 获取所有屏幕的几何范围
        screens = QApplication.screens()
        if not screens:
            self.setGeometry(0, 0, self.engine.width, self.engine.height)
        else:
            # 计算所有屏幕的总范围
            min_x = min(s.geometry().x() for s in screens)
            min_y = min(s.geometry().y() for s in screens)
            max_x = max(s.geometry().x() + s.geometry().width() for s in screens)
            max_y = max(s.geometry().y() + s.geometry().height() for s in screens)
            self.setGeometry(min_x, min_y, max_x - min_x, max_y - min_y)
            self.engine.width = max_x - min_x
            self.engine.height = max_y - min_y
            self.engine.track_height = self.engine.height // self.engine.tracks

        self.show()
        self.raise_()
        # 鼠标穿透（Win32）
        self._apply_click_through()
        print(f'[overlay] 全屏透明窗口: {self.engine.width}x{self.engine.height}, {self.engine.tracks}轨道', flush=True)

    def _apply_click_through(self):
        """Win32 鼠标穿透。"""
        if sys.platform != "win32":
            return
        try:
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_TOPMOST = 0x00000008
            styles = ctypes.windll.user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
            styles |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST
            ctypes.windll.user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, styles)
        except Exception as e:
            print(f'[overlay] 鼠标穿透失败: {e}', flush=True)

    def _get_track_y(self, track: int) -> int:
        th = self.engine.track_height
        # 只显示在屏幕顶部 30% 区域，不挡操作区
        max_y = int(self.engine.height * 0.3)
        actual_th = max_y // self.engine.tracks
        return track * actual_th + actual_th // 2 + 10

    def _find_safe_track(self, preferred: int, speed: float) -> int:
        """找一条时间上安全的轨道（同一轨道 2 秒内不发射）。"""
        now = time.time()
        cooldown = 2.0  # 发射间隔（秒）

        # 检查首选轨道
        last = self._track_last_emit.get(preferred, 0)
        if now - last >= cooldown:
            self._track_last_emit[preferred] = now
            return preferred

        # 检查其他轨道
        for t in range(self.engine.tracks):
            if t == preferred:
                continue
            last = self._track_last_emit.get(t, 0)
            if now - last >= cooldown:
                self._track_last_emit[t] = now
                return t

        # 都满的话用首选（强制）
        self._track_last_emit[preferred] = now
        return preferred

    def _track_is_safe(self, track: int, min_gap: float, screen_width: float) -> bool:
        """（保留兼容）"""
        return True

    def _track_rightmost(self, track: int) -> float:
        return self.engine.width

    def _tick(self):
        if not self.isVisible():
            return

        # 添加新弹幕（带轨道防重叠）
        batch = self.engine.drain()
        for d in batch:
            preferred_track = d['track']
            # 检查该轨道上最近的弹幕距离
            safe_track = self._find_safe_track(preferred_track, d['speed'])
            item = RenderItem(
                text=d['text'],
                color=d['color'],
                speed=d['speed'],
                track=safe_track,
                x=float(self.engine.width),
            )
            item.width = self.font_metrics.horizontalAdvance(d['text'])
            self.items.append(item)

        # 移动弹幕
        for item in self.items[:]:
            item.x -= item.speed
            if item.x < -(item.width + 100):
                item.visible = False
        self.items = [i for i in self.items if i.visible]

        if self.items:
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # 完全透明，不画任何背景
        # 只绘制弹幕文字（跳过屏幕外的）
        sw = self.engine.width
        for item in self.items:
            if item.x > sw + 200 or item.x + item.width < -200:
                continue
            y = self._get_track_y(item.track)
            # 阴影
            painter.setPen(QColor(0, 0, 0, 200))
            painter.setFont(self.font)
            painter.drawText(int(item.x) + 2, y + 2, item.text)
            # 正文
            rgb = self._hex_to_rgb(item.color)
            painter.setPen(QColor(*rgb))
            painter.drawText(int(item.x), y, item.text)

        painter.end()

    def _hex_to_rgb(self, hex_color: str) -> tuple:
        h = hex_color.lstrip('#')
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    def add_danmu(self, content: str, color: str = "#ffffff", track: int = 0):
        self.engine.add_danmu(content, color, track)

    def stop(self):
        self.engine.running = False
        self.timer.stop()
        self.close()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    engine = DanmuEngine(3840, 1080, tracks=10)
    overlay = DanmuOverlay(engine)
    overlay.show_fullscreen()

    def test():
        time.sleep(2)
        colors = ["#ffff00", "#00ff88", "#ff4444", "#4488ff", "#ffffff", "#ff6b6b", "#4ecdc4", "#ffd700"]
        for i in range(15):
            overlay.add_danmu(f"测试弹幕{i+1}", colors[i % len(colors)], i % 10)
            time.sleep(0.3)

    threading.Thread(target=test, daemon=True).start()
    sys.exit(app.exec())
