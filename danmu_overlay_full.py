"""
弹幕浮层 - 全屏透明版（合并增强）
覆盖整个屏幕，鼠标穿透，不影响游戏操作

合并来源：
- danmu_overlay_full.py：全屏多屏 + 鼠标穿透 + 碰撞检测 + 轨道冷却
- danmu_widget.py：预渲染 QPixmap + 淡入淡出 + 脏区优化 + 快速渲染

v2.0 · 2026-06-28 · 奥菲莉娅
"""
import sys
import time
import threading
import ctypes
from dataclasses import dataclass, field
from typing import Optional
from collections import deque

from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QTimer, QPoint, QElapsedTimer, QRectF
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPixmap, QPen


# ===== 常量 =====
_FADE_IN_PX = 80    # 右侧淡入区域（像素）
_FADE_OUT_PX = 60   # 左侧淡出区域（像素）
_INTERVAL_MS = 33   # ~30fps
_DT_CAP_SEC = 0.1   # 最大 dt 封顶
_FAST_RENDER_MIN_LEN = 36  # 长文本走快速渲染


# ===== 弹幕引擎 =====
class DanmuEngine:
    """弹幕引擎：维护队列 + 轨道数 + 屏幕尺寸。"""

    def __init__(self, width: int = 3840, height: int = 1080, tracks: int = 8):
        self.width = width
        self.height = height
        self.tracks = tracks
        self.track_height = height // tracks
        self.queue: deque = deque()
        self.running = True

    def add_danmu(self, content: str, color: str = "#ffffff", track: int = 0, speed: float = None):
        """添加一条弹幕到队列。"""
        if speed is None:
            speed = 6.0 + abs(hash(content + str(time.time()))) % 7
        self.queue.append({
            "text": content, "color": color,
            "speed": speed, "track": track % self.tracks
        })

    def drain(self) -> list:
        items = []
        while self.queue:
            items.append(self.queue.popleft())
        return items


# ===== 渲染项 =====
@dataclass
class RenderItem:
    text: str = ""
    color: str = "#ffffff"
    speed: float = 3.0
    track: int = 0
    x: float = 0.0
    width: float = 0.0
    visible: bool = True
    # 预渲染 pixmap（widget 带来的优化）
    _pixmap: Optional[QPixmap] = field(default=None, repr=False)
    # 淡入淡出 alpha 缓存
    _opacity_bucket: Optional[int] = field(default=None, repr=False)
    _cached_opacity: Optional[float] = field(default=None, repr=False)


# ===== 浮层 Widget =====
class DanmuOverlay(QWidget):
    """全屏透明弹幕浮层（合并 enhanced 版）。"""

    def __init__(self, engine: DanmuEngine):
        super().__init__()
        self.engine = engine
        self.items: list[RenderItem] = []
        self.font = QFont("Microsoft YaHei", 20, QFont.Weight.Bold)
        self.font_metrics = QFontMetrics(self.font)
        self._track_last_emit: dict = {}
        self._width_cache: dict[str, float] = {}
        self._tick_clock = QElapsedTimer()
        self._last_tick_valid = False
        self._last_tick_dt = 1.0 / 30.0

        # 窗口设置
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        # 定时器
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(_INTERVAL_MS)

    # ---- 文本宽度缓存 ----
    def _text_width(self, text: str) -> float:
        if text not in self._width_cache:
            self._width_cache[text] = self.font_metrics.horizontalAdvance(text)
        return self._width_cache[text]

    # ---- 全屏多屏 ----
    def show_fullscreen(self):
        screens = QApplication.screens()
        if not screens:
            self.setGeometry(0, 0, self.engine.width, self.engine.height)
        else:
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
        self._apply_click_through()
        print(f'[overlay] 全屏透明窗口: {self.engine.width}x{self.engine.height}, {self.engine.tracks}轨道', flush=True)

    # ---- Win32 鼠标穿透 ----
    def _apply_click_through(self):
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

    # ---- 轨道 Y 坐标 ----
    def _get_track_y(self, track: int) -> int:
        max_y = int(self.engine.height * 0.3)
        actual_th = max_y // self.engine.tracks
        return track * actual_th + actual_th // 2 + 10

    # ---- 碰撞检测 + 时间冷却 ----
    def _find_safe_track(self, preferred: int) -> int:
        now = time.time()
        cooldown = 2.0
        last = self._track_last_emit.get(preferred, 0)
        if now - last >= cooldown:
            self._track_last_emit[preferred] = now
            return preferred
        for t in range(self.engine.tracks):
            if t == preferred:
                continue
            last = self._track_last_emit.get(t, 0)
            if now - last >= cooldown:
                self._track_last_emit[t] = now
                return t
        self._track_last_emit[preferred] = now
        return preferred

    # ---- 淡入淡出 alpha ----
    def _item_opacity(self, item: RenderItem) -> float:
        sw = self.engine.width
        if sw <= 0:
            return 1.0
        bucket = int(item.x / 4.0)
        if item._opacity_bucket == bucket and item._cached_opacity is not None:
            return item._cached_opacity

        enter = 1.0
        if item.x > sw - _FADE_IN_PX:
            enter = max(0.0, min(1.0, (sw - item.x) / _FADE_IN_PX))
        exit_a = 1.0
        if item.x + item.width < _FADE_OUT_PX:
            exit_a = max(0.0, min(1.0, (item.x + item.width) / _FADE_OUT_PX))

        opacity = min(enter, exit_a)
        item._opacity_bucket = bucket
        item._cached_opacity = opacity
        return opacity

    # ---- 是否在绘制范围内 ----
    def _item_in_paint_band(self, item: RenderItem) -> bool:
        sw = self.engine.width
        if item.x >= sw + _FADE_IN_PX:
            return False
        if item.x + item.width <= 0:
            return False
        return True

    # ---- 快速渲染判断 ----
    def _use_fast_render(self, content: str) -> bool:
        if len(content) >= _FAST_RENDER_MIN_LEN:
            return True
        return any(ord(ch) > 127 for ch in content)

    # ---- 预渲染 pixmap ----
    def _render_pixmap(self, item: RenderItem) -> QPixmap:
        w = int(item.width) + 10
        h = self.font_metrics.height() + 10
        dpr = self.devicePixelRatio()
        pm = QPixmap(int(w * dpr), int(h * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pm)
        painter.setFont(self.font)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # 在 pixmap 内部渲染，从 (5, ascent+5) 开始
        ascent = self.font_metrics.ascent()
        fast = self._use_fast_render(item.text)
        if fast:
            # 快速渲染：8 方向描边
            outline = QPen(QColor(0, 0, 0, 200))
            offsets = [(-2, 0), (2, 0), (0, -2), (0, 2),
                       (-1, -1), (1, 1), (-1, 1), (1, -1)]
            for dx, dy in offsets:
                painter.setPen(outline)
                painter.drawText(5 + dx, ascent + 5 + dy, item.text)
            painter.setPen(QColor(*self._hex_to_rgb(item.color)))
            painter.drawText(5, ascent + 5, item.text)
        else:
            # 简单 drawText + 描边
            painter.setPen(QColor(0, 0, 0, 200))
            painter.drawText(5 + 2, ascent + 7, item.text)
            painter.setPen(QColor(*self._hex_to_rgb(item.color)))
            painter.drawText(5, ascent + 5, item.text)

        painter.end()
        return pm

    # ---- tick 循环 ----
    def _tick_dt(self) -> float:
        if not self._last_tick_valid:
            self._tick_clock.start()
            self._last_tick_valid = True
            return 1.0 / 30.0
        dt = self._tick_clock.elapsed() / 1000.0 - self._last_tick_dt
        if dt <= 0:
            dt = 1.0 / 30.0
        self._tick_clock.start()
        return min(dt, _DT_CAP_SEC)

    def _tick(self):
        if not self.isVisible():
            return

        # 添加新弹幕
        batch = self.engine.drain()
        for d in batch:
            safe_track = self._find_safe_track(d['track'])
            item = RenderItem(
                text=d['text'],
                color=d['color'],
                speed=d['speed'],
                track=safe_track,
                x=float(self.engine.width),
            )
            item.width = self._text_width(d['text'])
            self.items.append(item)

        # 移动弹幕
        for item in self.items[:]:
            item.x -= item.speed
            if item.x < -(item.width + 100):
                item.visible = False
        self.items = [i for i in self.items if i.visible]

        if self.items:
            self.update()

    # ---- paintEvent ----
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # 全透明背景
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))

        sw = self.engine.width
        for item in self.items:
            if not self._item_in_paint_band(item):
                continue
            if item.x > sw + 200 or item.x + item.width < -200:
                continue

            # 预渲染 pixmap（惰性）
            if item._pixmap is None:
                item._pixmap = self._render_pixmap(item)

            opacity = self._item_opacity(item)
            if opacity <= 0.0:
                continue

            painter.setOpacity(opacity)
            y = self._get_track_y(item.track)
            if item._pixmap:
                painter.drawPixmap(int(item.x), y, item._pixmap)
            else:
                rgb = self._hex_to_rgb(item.color)
                painter.setPen(QColor(0, 0, 0, 200))
                painter.setFont(self.font)
                painter.drawText(int(item.x) + 2, y + 2, item.text)
                painter.setPen(QColor(*rgb))
                painter.drawText(int(item.x), y, item.text)

        painter.setOpacity(1.0)
        painter.end()

    # ---- 公共接口 ----
    def add_danmu(self, content: str, color: str = "#ffffff", track: int = 0):
        self.engine.add_danmu(content, color, track)

    def stop(self):
        self.engine.running = False
        self.timer.stop()
        self.close()

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> tuple:
        h = hex_color.lstrip('#')
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    engine = DanmuEngine(3840, 1080, tracks=10)
    overlay = DanmuOverlay(engine)
    overlay.show_fullscreen()

    def test():
        time.sleep(2)
        colors = ["#ffff00", "#00ff88", "#ff4444", "#4488ff", "#ffffff",
                  "#ff6b6b", "#4ecdc4", "#ffd700", "#a29bfe", "#fd79a8"]
        for i in range(20):
            overlay.add_danmu(f"测试弹幕{i+1} 合并增强版", colors[i % len(colors)], i % 10)
            time.sleep(0.3)

    threading.Thread(target=test, daemon=True).start()
    sys.exit(app.exec())
