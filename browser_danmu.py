"""
极简弹幕显示 - 用浏览器窗口替代 PyQt5 浮层
"""
import threading
import time
import json
from pathlib import Path

# 弹幕存储
DANMU_FILE = Path(__file__).parent / ".danmu_buffer.json"

def save_danmu(text, danmu_type="comment"):
    """保存弹幕到文件"""
    entry = {"text": text, "type": danmu_type, "time": time.time()}
    buffer = []
    if DANMU_FILE.exists():
        try:
            buffer = json.loads(DANMU_FILE.read_text(encoding="utf-8"))
        except:
            buffer = []
    buffer.append(entry)
    # 只保留最近 50 条
    buffer = buffer[-50:]
    DANMU_FILE.write_text(json.dumps(buffer, ensure_ascii=False, indent=2), encoding="utf-8")

def get_danmu_html():
    """生成弹幕显示的 HTML"""
    buffer = []
    if DANMU_FILE.exists():
        try:
            buffer = json.loads(DANMU_FILE.read_text(encoding="utf-8"))
        except:
            pass
    
    items = ""
    for d in buffer[-10:]:
        color = "#FFFFFF"
        if d.get("type") == "meme":
            color = "#FF6B6B"
        elif d.get("type") == "reaction":
            color = "#4ECDC4"
        items += f'<div class="danmu" style="color:{color};">{d["text"]}</div>\n'
    
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    body {{ margin: 0; padding: 0; overflow: hidden; background: transparent; font-family: "Microsoft YaHei"; }}
    .danmu {{
        position: absolute;
        white-space: nowrap;
        font-size: 18px;
        font-weight: bold;
        text-shadow: 1px 1px 2px rgba(0,0,0,0.8);
        opacity: 0.9;
    }}
    .status {{
        position: fixed;
        bottom: 10px;
        left: 10px;
        color: rgba(255,255,255,0.5);
        font-size: 12px;
    }}
</style>
</head>
<body>
{items}
<div class="status" id="status">弹幕浮层已就绪</div>
<script>
    // 自动隐藏旧弹幕
    setInterval(() => {{
        const danmus = document.querySelectorAll('.danmu');
        danmus.forEach((d, i) => {{
            if (i < danmus.length - 5) d.style.display = 'none';
        }});
    }}, 5000);
</script>
</body>
</html>"""

def show_browser():
    """用默认浏览器显示弹幕"""
    import subprocess
    html_path = (Path(__file__).parent / ".danmu_display.html").resolve()
    html_path.write_text(get_danmu_html(), encoding="utf-8")
    subprocess.Popen(['start', html_path.as_uri()], shell=True)

if __name__ == "__main__":
    show_browser()
    print("浏览器已打开，显示弹幕。按 Ctrl+C 退出")
    try:
        while True:
            time.sleep(1)
            # 刷新 HTML
            html_path = Path(__file__).parent / ".danmu_display.html"
            html_path.write_text(get_danmu_html(), encoding="utf-8")
    except KeyboardInterrupt:
        pass
