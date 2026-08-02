"""
系统托盘 + 全局快捷键
"""
import threading
import time
import keyboard
from PIL import Image
import pystray

class TrayIcon:
    def __init__(self, on_toggle=None, on_pause=None, on_exit=None):
        self.on_toggle = on_toggle
        self.on_pause = on_pause
        self.on_exit = on_exit
        self.running = False
        self.paused = False
        self.icon = None
        self._thread = None

    def _create_menu(self):
        return pystray.Menu(
            pystray.MenuItem("显示/隐藏 弹幕 (F9)", self._toggle, default=True),
            pystray.MenuItem("暂停/恢复 弹幕", self._pause_resume),
            pystray.MenuItem("退出", self._exit),
        )

    def _toggle(self, icon=None, item=None):
        if self.on_toggle:
            self.on_toggle()
        self._update_icon()

    def _pause_resume(self, icon=None, item=None):
        if self.on_pause:
            self.on_pause()
        self._update_icon()

    def _exit(self, icon=None, item=None):
        print('[tray] 退出中...', flush=True)
        self.stop()
        if self.on_exit:
            self.on_exit()

    def _update_icon(self):
        if not self.icon:
            return
        # 不同状态用不同颜色
        if self.paused:
            color = (255, 100, 100, 255)  # 红色 = 暂停
        else:
            color = (0, 255, 136, 255)   # 绿色 = 运行
        img = Image.new('RGBA', (64, 64), (0,0,0,0))
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        draw.ellipse([4,4,60,60], fill=color, outline=(255,255,255,200), width=2)
        draw.rectangle([20,10,44,54], fill='#333333')
        self.icon.icon = img

    def start(self):
        """在后台线程启动托盘。"""
        self.running = True
        img = Image.new('RGBA', (64, 64), (0,0,0,0))
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        draw.ellipse([4,4,60,60], fill='#00ff88', outline=(255,255,255,200), width=2)
        draw.rectangle([20,10,44,54], fill='#333333')

        self.icon = pystray.Icon("danmu", img, "AI 弹幕助手", self._create_menu())
        self.icon.visible = True

        # 全局快捷键 F9
        def on_f9():
            if self.running:
                self._toggle()
        keyboard.add_hotkey('f9', on_f9)

        self._thread = threading.Thread(target=self.icon.run, daemon=True)
        self._thread.start()
        print('[tray] 托盘已启动，按 F9 切换显示/隐藏', flush=True)

    def stop(self):
        self.running = False
        if self.icon:
            self.icon.stop()
        keyboard.unhook_all()

    def is_paused(self):
        return self.paused
