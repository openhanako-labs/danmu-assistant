"""测试弹幕浮层是否可见"""
import sys
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QFont, QColor

app = QApplication(sys.argv)

# 创建一个全屏半透明窗口测试可见性
w = QWidget()
w.setWindowFlags(
    Qt.WindowType.FramelessWindowHint
    | Qt.WindowType.WindowStaysOnTopHint
    | Qt.WindowType.Tool
    | Qt.WindowType.BypassWindowManagerHint
)
w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
w.resize(1920, 1080)

# 画个明显的测试标记
w.paint_callback = lambda p: (
    p.setPen(QColor(255, 100, 100)),
    p.setFont(QFont("Microsoft YaHei", 48, QFont.Weight.Bold)),
    p.drawText(100, 100, "弹幕浮层可见测试！")
)

def paintEvent(ev):
    p = QPainter(w)
    p.fillRect(w.rect(), QColor(0, 0, 0, 80))  # 半透明黑色背景
    p.setPen(QColor(255, 100, 100))
    p.setFont(QFont("Microsoft YaHei", 48, QFont.Weight.Bold))
    p.drawText(100, 100, "弹幕浮层可见测试！")

w.paintEvent = paintEvent
w.show()

print("[TEST] 窗口已 show()，如果你能看到半透明黑色背景和红色文字，说明浮层渲染正常", flush=True)

import time
time.sleep(5)
print("[TEST] 5秒后退出", flush=True)
sys.exit(0)
