"""
弹幕浮层 - tkinter 版
纯 Tkinter 实现，不依赖 pywebview/WebView2
"""
import sys
import time
import threading
import tkinter as tk
from tkinter import font as tkfont
from dataclasses import dataclass
from collections import deque


@dataclass
class DanmuItem:
    content: str
    color: str = "#ffffff"
    speed: float = 4.0
    x: float = 0.0
    y: float = 0.0
    visible: bool = True


class DanmuEngine:
    def __init__(self, width: int = 600, height: int = 80):
        self.width = width
        self.height = height
        self.queue: deque = deque()
        self.running = True

    def add_danmu(self, content: str, color: str = "#ffffff"):
        speed = 1.5 + abs(hash(content)) % 3  # 1.5~4.5 px/frame
        self.queue.append(DanmuItem(content=content, color=color, speed=speed))

    def drain(self) -> list:
        items = []
        while self.queue:
            d = self.queue.popleft()
            items.append({"text": d.content, "color": d.color, "speed": d.speed})
        return items


class DanmuOverlay:
    """Tkinter 弹幕浮层。"""

    def __init__(self, engine: DanmuEngine):
        self.engine = engine
        self.master = None
        self.canvas = None
        self.items: list[dict] = []
        self._running = False
        self._y_base = 18  # 弹幕基线 Y（靠近顶部）

    def show(self, x: int = 600, y: int = 400):
        """显示窗口。"""
        self.master = tk.Tk()
        self.master.overrideredirect(True)  # 无边框
        self.master.attributes("-topmost", True)  # 置顶
        self.master.attributes("-alpha", 0.85)  # 半透明
        self.master.configure(bg='black')
        self.master.geometry(f"{self.engine.width}x{self.engine.height}+{x}+{y}")

        self.canvas = tk.Canvas(
            self.master, bg='black', highlightthickness=0,
            width=self.engine.width, height=self.engine.height
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.font = tkfont.Font(family="Microsoft YaHei", size=18, weight="bold")
        self._running = True
        self._update_loop()

    def _update_loop(self):
        """60fps 更新循环。"""
        if not self._running:
            return

        # 从队列添加新弹幕
        batch = self.engine.drain()
        for d in batch:
            # 先画黑色阴影（偏移2像素）
            shadow_cid = self.canvas.create_text(
                self.engine.width + 2, self._y_base + 2,
                text=d['text'],
                fill='black',
                font=self.font,
                anchor=tk.CENTER,
            )
            # 再画正文
            cid = self.canvas.create_text(
                self.engine.width, self._y_base,
                text=d['text'],
                fill=d['color'],
                font=self.font,
                anchor=tk.CENTER,
            )
            self.items.append({
                'canvas_id': cid,
                'shadow_id': shadow_cid,
                'speed': d['speed'],
                'x': float(self.engine.width),
            })

        # 移动所有弹幕
        for item in self.items[:]:
            item['x'] -= item['speed']
            self.canvas.coords(item['canvas_id'], item['x'], self._y_base)
            self.canvas.coords(item['shadow_id'], item['x'] + 2, self._y_base + 2)
            if item['x'] < -300:
                self.canvas.delete(item['canvas_id'])
                self.canvas.delete(item['shadow_id'])
                self.items.remove(item)

        self.master.after(16, self._update_loop)  # ~60fps

    def add_danmu(self, content: str, color: str = "#ffffff"):
        self.engine.add_danmu(content, color)

    def stop(self):
        self._running = False
        self.engine.running = False
        if self.master:
            self.master.destroy()


if __name__ == "__main__":
    engine = DanmuEngine(600, 80)
    overlay = DanmuOverlay(engine)
    overlay.show()

    def test():
        time.sleep(2)
        overlay.add_danmu("黄色弹幕", "#ffff00")
        time.sleep(0.8)
        overlay.add_danmu("绿色弹幕", "#00ff88")
        time.sleep(0.8)
        overlay.add_danmu("红色弹幕", "#ff4444")
        time.sleep(0.8)
        overlay.add_danmu("蓝色弹幕", "#4488ff")

    threading.Thread(target=test, daemon=True).start()

    overlay.master.mainloop()
