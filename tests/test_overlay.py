"""
弹幕浮层 - 独立测试
双击运行，应该弹出一个黑色窄条窗口，里面弹幕从右往左飘
"""
import time
import threading
import webview

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

if __name__ == "__main__":
    print("正在创建弹幕浮层窗口...", flush=True)
    
    window = webview.create_window(
        title='弹幕浮层',
        html=DANMU_HTML,
        width=1920,
        height=80,
        x=400,
        y=300,
        resizable=False,
        frameless=False,
        easy_drag=True,
        background_color='#000000',
    )
    
    window.events.loaded += lambda: print("[OK] 窗口已加载", flush=True)
    
    # 测试弹幕
    def send_test_danmu():
        time.sleep(2)
        window.evaluate_js("window.addDanmu('黄色弹幕', '#ffff00', 5)")
        time.sleep(0.8)
        window.evaluate_js("window.addDanmu('绿色弹幕', '#00ff88', 4)")
        time.sleep(0.8)
        window.evaluate_js("window.addDanmu('红色弹幕', '#ff4444', 6)")
        time.sleep(0.8)
        window.evaluate_js("window.addDanmu('蓝色弹幕', '#4488ff', 3)")
        time.sleep(0.8)
        window.evaluate_js("window.addDanmu('白色弹幕', '#ffffff', 4.5)")
        print("[OK] 测试弹幕已发送", flush=True)
    
    threading.Thread(target=send_test_danmu, daemon=True).start()
    
    print("窗口已创建，请查看屏幕...", flush=True)
    webview.start(debug=False)
