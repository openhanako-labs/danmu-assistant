"""
弹幕浮层 - pywebview 版
"""
import sys
import time
import threading
from dataclasses import dataclass
from collections import deque
from typing import Optional

import webview
from webview import Window


@dataclass
class DanmuItem:
    content: str
    color: str = "#ffffff"
    speed: float = 4.0


class DanmuEngine:
    def __init__(self, screen_width: float = 1920.0, screen_height: float = 80.0):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.queue: deque = deque()
        self.running = True

    def set_screen_size(self, w: float, h: float):
        self.screen_width = w
        self.screen_height = h

    def add_danmu(self, content: str, color: str = "#ffffff"):
        speed = 3.0 + abs(hash(content)) % 3
        self.queue.append(DanmuItem(content=content, color=color, speed=speed))

    def drain(self) -> list:
        items = []
        while self.queue:
            d = self.queue.popleft()
            items.append({"text": d.content, "color": d.color, "speed": d.speed})
        return items


DANMU_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body {
    width: 100%; height: 100%;
    overflow: hidden;
    background: rgba(0, 0, 0, 0.75);
    font-family: "Microsoft YaHei", sans-serif;
}
#container {
    position: relative;
    width: 100%; height: 100%;
}
.danmu {
    position: absolute;
    white-space: nowrap;
    font-size: 20px;
    font-weight: bold;
    text-shadow: 1px 1px 3px rgba(0,0,0,0.9);
    pointer-events: none;
}
</style>
</head>
<body>
<div id="container"></div>
<script>
(function() {
    const container = document.getElementById('container');
    const items = [];
    let animating = false;
    let lastTime = 0;

    function addDanmu(text, color, speed) {
        const el = document.createElement('div');
        el.className = 'danmu';
        el.textContent = text;
        el.style.color = color || '#ffffff';
        const trackH = 24;
        const trackCount = Math.max(1, Math.floor(window.innerHeight / trackH));
        const track = Math.floor(Math.random() * trackCount);
        el.style.top = (track * trackH + 2) + 'px';
        el.style.transform = 'translateX(' + window.innerWidth + 'px)';
        container.appendChild(el);
        items.push({ el, speed: speed || 4 });
        if (!animating) {
            animating = true;
            lastTime = performance.now();
            requestAnimationFrame(tick);
        }
    }

    function tick(now) {
        const dt = (now - lastTime) / 1000;
        lastTime = now;
        for (let i = items.length - 1; i >= 0; i--) {
            const item = items[i];
            const cur = parseFloat(item.el.style.transform.replace('translateX(', '').replace('px)', ''));
            const nx = cur - item.speed * dt * 60;
            item.el.style.transform = 'translateX(' + nx + 'px)';
            if (nx < -500) {
                item.el.remove();
                items.splice(i, 1);
            }
        }
        if (items.length > 0) {
            requestAnimationFrame(tick);
        } else {
            animating = false;
        }
    }

    window.addDanmu = addDanmu;
})();
</script>
</body>
</html>
"""


class DanmuOverlayWebView:
    def __init__(self, engine: DanmuEngine):
        self.engine = engine
        self.window: Optional[Window] = None
        self._js_ready = threading.Event()

    def show(self):
        # 用 1920x80 小窗口，放在屏幕中央偏下
        screen_w = 600
        screen_h = 100
        self.engine.set_screen_size(screen_w, screen_h)

        class PingAPI:
            def ping(self):
                return "ok"

        self.window = webview.create_window(
            title='弹幕浮层',
            html=DANMU_HTML,
            width=screen_w,
            height=screen_h,
            x=600,
            y=400,
            resizable=False,
            fullscreen=False,
            frameless=False,
            easy_drag=True,
            js_api=PingAPI(),
            background_color='#000000',
        )

        try:
            self.window.topmost = True
        except Exception:
            pass

        self.window.events.loaded += self._on_loaded
        print(f'[overlay] 窗口: x=600, y=400, w={screen_w}, h={screen_h}', flush=True)

        # 弹幕注入线程
        self._start_inject_thread()

    def _on_loaded(self):
        self._js_ready.set()
        print('[overlay] JS ready', flush=True)

    def _start_inject_thread(self):
        def inject_loop():
            while self.engine.running:
                time.sleep(0.1)
                batch = self.engine.drain()
                if batch and self._js_ready.is_set() and self.window:
                    for d in batch:
                        safe = d['text'].replace("'", "\\'")
                        js = f"window.addDanmu('{safe}', '{d['color']}', {d['speed']});"
                        try:
                            self.window.evaluate_js(js)
                        except Exception as e:
                            print(f'[WARN] eval_js: {e}', flush=True)

        t = threading.Thread(target=inject_loop, daemon=True)
        t.start()

    def add_danmu(self, content: str, color: str = "#ffffff"):
        self.engine.add_danmu(content, color)

    def stop(self):
        self.engine.running = False
        if self.window:
            self.window.destroy()


if __name__ == "__main__":
    engine = DanmuEngine()
    overlay = DanmuOverlayWebView(engine)
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

    webview.start(debug=False)
