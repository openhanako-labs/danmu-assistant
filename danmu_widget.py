"""
弹幕浮层 PyQt6 版 — 基于 danmuai 架构

核心特性：
- 全屏透明置顶 QWidget，60fps 脏区重绘
- Win32 WS_EX_LAYERED | WS_EX_TRANSPARENT 鼠标穿透
- 弹幕文本预渲染为 QPixmap（描边+填充）
- 淡入/淡出 alpha 分段
- 支持多轨道（layout_mode）
"""
import logging
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import (
    QElapsedTimer, QPointF, QRect, QRectF, Qt, QTimer,
)
from PyQt6.QtGui import (
    QColor, QFont, QFontMetrics, QPainter, QPainterPath,
    QPen, QPixmap, QWindow,
)

logger = logging.getLogger("danmu.overlay")

# --- 常量 ---
_FRAME_DT = 1.0 / 60.0
_INTERVAL_MS = 16  # 16ms = 60fps
_DT_CAP_SEC = 0.1
_FADE_IN_PX = 80
_FADE_OUT_PX = 60
_DIRTY_MARGIN_PX = 12
_PRERENDER_AHEAD_PX = _FADE_IN_PX + 80
_Y_OFFSET = 30
_FAST_DANMU_RENDER_MIN_LEN = 36
_FAST_OUTLINE_OFFSETS = (
    (-2, 0), (2, 0), (0, -2), (0, 2),
    (-1, -1), (1, 1), (-1, 1), (1, -1),
)
_OPACITY_CACHE_BUCKET = 4.0


# --- Win32 辅助 ---
def _apply_overlay_exstyles(hwnd: int, click_through: bool = True):
    """设置 WS_EX_LAYERED | WS_EX_TRANSPARENT 实现鼠标穿透。"""
    if sys.platform != "win32":
        return
    import ctypes
    GWL_EXSTYLE = -20
    WS_EX_LAYERED = 0x00080000
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_TOPMOST = 0x00000008

    styles = ctypes.windll.user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    if click_through:
        styles |= WS_EX_LAYERED | WS_EX_TRANSPARENT
    else:
        styles |= WS_EX_LAYERED
    ctypes.windll.user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, styles)


def _reassert_hwnd_topmost(hwnd: int):
    """恢复 HWND_TOPMOST z-order。"""
    if sys.platform != "win32":
        return
    import ctypes
    SWP_NOMOVE = 0x0002
    SWP_NOSIZE = 0x0001
    HWND_TOPMOST = -1
    SWP_NOACTIVATE = 0x0010
    ctypes.windll.user32.SetWindowPos(
        hwnd, HWND_TOPMOST, 0, 0, 0, 0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
    )


# --- 弹幕数据 ---
@dataclass
class DanmuItem:
    content: str
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    speed: float = 4.0  # px/sec
    color: QColor = field(default_factory=lambda: QColor(255, 255, 255))
    _pixmap: Optional[QPixmap] = None
    _opacity_cache_bucket: Optional[int] = None
    _cached_opacity: Optional[float] = None
    track_index: int = 0
    visible: bool = True


# --- 快速渲染判断 ---
def _use_fast_danmu_render(content: str) -> bool:
    """长文本/emoji 走 drawText 描边，避免 QPainterPath 阻塞。"""
    if len(content) >= _FAST_DANMU_RENDER_MIN_LEN:
        return True
    return any(ord(ch) > 127 for ch in content)


def _paint_danmu_text(
    painter: QPainter,
    *,
    content: str,
    font: QFont,
    color: QColor,
    text_x: int,
    baseline_y: int,
    fast: bool,
) -> None:
    if fast:
        outline_pen = QPen(QColor(0, 0, 0, 200))
        for dx, dy in _FAST_OUTLINE_OFFSETS:
            painter.setPen(outline_pen)
            painter.drawText(text_x + dx, baseline_y + dy, content)
        painter.setPen(QPen(color))
        painter.drawText(text_x, baseline_y, content)
        return

    path = QPainterPath()
    path.addText(text_x, baseline_y, font, content)
    outline_pen = QPen(QColor(0, 0, 0, 200))
    outline_pen.setWidth(4)
    outline_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    outline_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(outline_pen)
    painter.drawPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawPath(path)


# --- 弹幕引擎（极简版，只负责移动） ---
class DanmuEngine:
    """极简弹幕引擎：维护 track + item 位置，支持 move。"""

    def __init__(self, screen_width: float = 1920.0, screen_height: float = 1080.0):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.tracks: list[list[DanmuItem]] = [[] for _ in range(8)]  # 8 轨道
        self.running = True

    def set_screen_width(self, w: float):
        self.screen_width = w

    def set_screen_height(self, h: float):
        self.screen_height = h

    def add_item(self, content: str, color: QColor = None, track_index: int = 0) -> DanmuItem:
        if color is None:
            color = QColor(255, 255, 255)
        item = DanmuItem(
            content=content,
            x=self.screen_width,
            y=0.0,
            speed=3.0 + hash(content) % 3,  # 3-5 px/sec
            color=color,
            track_index=track_index % len(self.tracks),
        )
        self.tracks[item.track_index].append(item)
        return item

    def update(self, dt_sec: float):
        """更新所有 item 位置。"""
        for track in self.tracks:
            for item in track:
                item.x -= item.speed * dt_sec
                # 移出屏幕左侧，标记不可见
                if item.x + item.width < 0:
                    item.visible = False

    def visible_display_count(self) -> int:
        count = 0
        for track in self.tracks:
            for item in track:
                if item.visible and item.x < self.screen_width:
                    count += 1
        return count

    def needs_render_tick(self) -> bool:
        """还有可动画内容。"""
        for track in self.tracks:
            for item in track:
                if item.visible and item.x < self.screen_width + _FADE_IN_PX:
                    return True
        return False

    def current_display_count(self) -> int:
        total = 0
        for track in self.tracks:
            total += len(track)
        return total


# --- 浮层 Widget ---
class DanmuOverlay(QWidget):
    """透明置顶弹幕渲染层。"""

    def __init__(self, engine: DanmuEngine):
        super().__init__()
        self.engine = engine

        # 窗口标志
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.BypassWindowManagerHint
        )
        # 不用 WA_TranslucentBackground——在某些显卡驱动下窗口会完全不可见
        # 改用深色半透明背景条，底部固定区域
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # 字体
        self.font = QFont("Microsoft YaHei", 16)
        self.font.setBold(False)
        self.font_metrics = QFontMetrics(self.font)

        # 屏幕
        self._screen_width: float = 0.0
        self._timer_interval_ms = _INTERVAL_MS

        # 渲染循环
        self._tick_clock = QElapsedTimer()
        self._last_tick_valid = False
        self.last_tick_dt_sec: float = _FRAME_DT

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._tick)

    def _apply_win32_click_through(self):
        if sys.platform != "win32":
            return
        try:
            hwnd = int(self.winId())
            _apply_overlay_exstyles(hwnd, click_through=True)
        except Exception as e:
            logger.warning("apply_win32_click_through failed: %s", e)

    def reassert_topmost_zorder(self):
        if not self.isVisible():
            return
        self.raise_()
        try:
            hwnd = int(self.winId())
            _reassert_hwnd_topmost(hwnd)
        except Exception:
            pass

    def show_for_screen(self, screen_index: int = 0):
        """对齐指定显示器 geometry，底部窄条模式。"""
        try:
            screens = QApplication.screens()
            if screens:
                screen_index = max(0, min(int(screen_index), len(screens) - 1))
                geo = screens[screen_index].geometry()
                # 底部窄条：全屏宽，高度 80px
                bar_height = 80
                self.setGeometry(geo.x(), geo.bottom() - bar_height, geo.width(), bar_height)
                self._screen_width = float(geo.width())
                self.engine.set_screen_width(self._screen_width)
                self.engine.set_screen_height(float(bar_height))
        except Exception as e:
            print(f'[WARN] show_for_screen error: {e}', flush=True)
            self.setGeometry(0, 1000, 1920, 80)
            self._screen_width = 1920.0
            self.engine.set_screen_width(1920.0)
            self.engine.set_screen_height(80.0)

        self._apply_font_from_config()
        self.show()

    def _apply_font_from_config(self):
        self.font = QFont("Microsoft YaHei", 16)
        self.font.setBold(False)
        self.font_metrics = QFontMetrics(self.font)

    def measure_item_width(self, item: DanmuItem):
        item.width = float(self.font_metrics.horizontalAdvance(item.content))

    def prepare_item_pixmap(self, item: DanmuItem):
        if item.width <= 0:
            self.measure_item_width(item)
        if item._pixmap is None:
            fast = _use_fast_danmu_render(item.content)
            item._pixmap = self._render_item_pixmap(item, fast=fast)

    def _render_item_pixmap(self, item: DanmuItem, *, fast: bool = False) -> QPixmap:
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

        baseline_y = self.font_metrics.ascent() + 5
        text_x = 5
        _paint_danmu_text(
            painter,
            content=item.content,
            font=self.font,
            color=item.color,
            text_x=text_x,
            baseline_y=baseline_y,
            fast=fast,
        )
        painter.end()
        return pm

    def _item_opacity(self, item: DanmuItem) -> float:
        screen_width = self._screen_width or float(self.width())
        if screen_width <= 0:
            return 1.0

        bucket = int(item.x / _OPACITY_CACHE_BUCKET)
        if getattr(item, "_opacity_cache_bucket", None) == bucket:
            cached = getattr(item, "_cached_opacity", None)
            if cached is not None:
                return cached

        enter_alpha = 1.0
        if item.x > screen_width - _FADE_IN_PX:
            enter_alpha = max(0.0, min(1.0, (screen_width - item.x) / _FADE_IN_PX))

        exit_alpha = 1.0
        right_edge = item.x + item.width
        if right_edge < _FADE_OUT_PX:
            exit_alpha = max(0.0, min(1.0, right_edge / _FADE_OUT_PX))

        opacity = min(enter_alpha, exit_alpha)
        item._opacity_cache_bucket = bucket
        item._cached_opacity = opacity
        return opacity

    def _item_in_paint_band(self, item: DanmuItem) -> bool:
        sw = self._screen_width or float(self.width())
        if sw <= 0:
            return True
        if item.x >= sw + _FADE_IN_PX:
            return False
        if item.x + item.width <= 0:
            return False
        return True

    def _tick_dt_sec(self) -> float:
        if not self._last_tick_valid:
            self._tick_clock.start()
            self._last_tick_valid = True
            return _FRAME_DT
        dt = self._tick_clock.restart() / 1000.0
        if dt <= 0.0:
            return _FRAME_DT
        return min(dt, _DT_CAP_SEC)

    def _tick(self):
        if not self.isVisible():
            return
        if not self.engine.needs_render_tick():
            self.timer.stop()
            return

        dt = self._tick_dt_sec()
        self.last_tick_dt_sec = dt
        self.engine.update(dt)

        # 预渲染可见区域的 pixmap
        for track in self.engine.tracks:
            for item in track:
                if item._pixmap is None and self._item_in_paint_band(item):
                    self.prepare_item_pixmap(item)

        # 脏区绘制
        margin = _DIRTY_MARGIN_PX
        dirty_items = []
        for track in self.engine.tracks:
            for item in track:
                if not self._item_in_paint_band(item):
                    continue
                sw = self._screen_width or float(self.width())
                right = item.x + item.width + margin
                left = item.x - margin
                if right > 0 and left < sw:
                    dirty_items.append(item)

        if dirty_items:
            bounds = None
            for item in dirty_items:
                w = item.width + 10
                h = self.font_metrics.height() + 10
                rect = QRectF(item.x, item.y + _Y_OFFSET, w, h)
                bounds = rect if bounds is None else bounds.united(rect)

            if bounds is not None:
                m = margin + _DIRTY_MARGIN_PX
                dirty = QRect(
                    int(bounds.left()) - int(m),
                    int(bounds.top()) - int(m),
                    int(bounds.width()) + int(2 * m),
                    int(bounds.height()) + int(2 * m),
                ).intersected(self.rect())
                if not dirty.isEmpty():
                    self.update(dirty)
                else:
                    self.update()
            else:
                self.update()
        else:
            self.update()

        if not self.engine.needs_render_tick():
            self.timer.stop()

    def start_render_loop(self):
        if not self.isVisible():
            return
        if not self.timer.isActive():
            self.timer.start(self._timer_interval_ms)
        self._tick()

    def stop_render_loop(self):
        self.timer.stop()
        self._last_tick_valid = False

    def ensure_render_loop(self):
        if self.isVisible() and self.engine.needs_render_tick():
            self.start_render_loop()

    def showEvent(self, event):
        try:
            super().showEvent(event)
            if self.engine.running:
                self.ensure_render_loop()
        except Exception as e:
            import traceback
            traceback.print_exc()

    def hideEvent(self, event):
        self.stop_render_loop()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # 底部半透明深色背景条
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))

        # 测试文字：确认 paintEvent 被调用
        painter.setFont(QFont("Microsoft YaHei", 18, QFont.Weight.Bold))
        painter.setPen(QColor(255, 255, 100))
        painter.drawText(10, self.height() - 15, "[弹幕浮层] ")

        # 从下到上遍历轨道
        for track in self.engine.tracks:
            for item in track:
                if not self._item_in_paint_band(item):
                    continue
                if item._pixmap is None:
                    self.prepare_item_pixmap(item)

                item_rect = QRectF(item.x, item.y + _Y_OFFSET,
                                   item.width + 10, self.font_metrics.height() + 10)
                if item_rect.left() < -50 or item_rect.right() > self.width() + 50:
                    continue

                opacity = self._item_opacity(item)
                if opacity <= 0.0:
                    continue

                painter.setOpacity(opacity)
                painter.drawPixmap(QPointF(item.x, item.y + _Y_OFFSET), item._pixmap)

        painter.setOpacity(1.0)
        painter.end()

    def add_danmu(self, content: str, color: QColor = None, track_index: int = 0) -> Optional[DanmuItem]:
        """添加弹幕，返回 item。"""
        item = self.engine.add_item(content, color, track_index)
        self.measure_item_width(item)
        self.prepare_item_pixmap(item)
        self.ensure_render_loop()
        return item
