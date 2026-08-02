"""
AI 弹幕助手 - 主入口
截屏 + AI 视觉模型 + 全屏透明浮层 + 文件弹幕源 + 语音理解弹幕
退出时生成完整弹幕统计
"""
import sys
import time
import random
import signal
import argparse
import logging
import yaml
import json
import threading
import queue
from queue import Queue
from datetime import datetime
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from danmu_stats_panel import DanmuStatsPanel
from danmu_overlay_full import DanmuOverlay, DanmuEngine
from danmu_file_source import DanmuFileSource
from danmu_ai import DanmuAI
from voice_danmu import VoiceDanmu
from buddy_source import BuddyDanmuSource
from idle_monitor import IdleMonitor
from blivedm_client import BiliLiveClient
from websocket_server import WSServer

# logging 配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

# SSRF 防护：允许的 API 域名白名单
ALLOWED_API_HOSTS = {
    "api.siliconflow.cn",
    "api.stepfun.com",
    "api.openai.com",
    "localhost",
    "127.0.0.1",
}


def validate_api_url(url: str):
    """校验 API URL，防止 SSRF 注入。"""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http"):
        raise ValueError(f"不支持的协议: {parsed.scheme}（只允许 https/http）")
    hostname = parsed.hostname or ""
    if hostname not in ALLOWED_API_HOSTS and not hostname.endswith(".openai.com"):
        raise ValueError(f"未授权的 API 域名: {hostname}")


def load_config(config_path: str = "config.yaml") -> dict:
    import sys as _sys
    base = Path(getattr(_sys, '_MEIPASS', Path(__file__).parent))
    p = base / config_path
    if not p.exists():
        p = Path(config_path)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        # 校验 API URL（SSRF 防护）
        for section in ("vision_api",):
            if section in cfg:
                url = cfg[section].get("base_url", "")
                if url:
                    try:
                        validate_api_url(url)
                    except ValueError as e:
                        logging.getLogger("main").warning(f"config {section}.base_url 校验失败: {e}，已禁用该功能")
                        cfg[section]["enabled"] = False
        return cfg
    return {}


COLOR_POOL = [
    "#ff6b6b", "#4ecdc4", "#ffd700", "#ffffff",
    "#ff9f43", "#a29bfe", "#fd79a8", "#00cec9",
]
COMMON_WORDS = ["太帅了", "666", "露西亚", "yyds", "哈哈", "特效", "难过", "气死", "哭哭", "无语", "太强了", "绝了", "老婆", "技能"]


# ═══════════════════════════════
#  HTTP 控制层（Hana 插件 / 外部系统对接）
# ═══════════════════════════════

# 模块级共享状态，由 main() 填充，HTTP Handler 读取
_app_state = {
    "ai": None,
    "voice": None,
    "file_source": None,
    "buddy": None,
    "idle_monitor": None,
    "overlay": None,
    "engine": None,
    "config": {},
    "history": [],
    "add_danmu": None,
    "hana_mode": False,
    "start_time": None,
    "idle_paused": False,
}


class DanmuHTTPHandler(BaseHTTPRequestHandler):
    """HTTP 控制接口——给 Hana 插件层或外部系统提供控制能力。"""

    def log_message(self, format, *args):
        pass  # 静默 HTTP 日志

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _cors(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > 0:
            return json.loads(self.rfile.read(length))
        return {}

    def do_OPTIONS(self):
        self._cors()

    def do_GET(self):
        ai = _app_state["ai"]
        voice = _app_state["voice"]
        file_source = _app_state["file_source"]
        history = _app_state["history"]
        config = _app_state["config"]

        if self.path == "/" or self.path == "":
            running = ai.running if ai else False
            voice_on = voice is not None and voice.running
            file_on = file_source is not None
            style = config.get("danmu_ai_style", "pi")
            elapsed = (datetime.now() - _app_state["start_time"]).total_seconds() if _app_state["start_time"] else 0
            density = len(history) / max(elapsed / 60, 1)
            idle_threshold = config.get("idle_threshold", 600)
            vision_cfg = config.get("vision_api", {})
            voice_cfg = config.get("voice", {})
            asr_cfg = voice_cfg.get("asr_api", {})
            all_styles = DanmuAI.list_styles() if 'DanmuAI' in dir() else []

            style_options = ""
            for sid, sdesc in all_styles:
                sel = ' selected' if sid == style else ''
                style_options += f'<option value="{sid}"{sel}>{sdesc}</option>'

            html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>AI 弹幕助手</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:system-ui,-apple-system,"Microsoft YaHei",sans-serif;background:#111;color:#eee;padding:20px;max-width:520px;margin:0 auto}}
h1{{font-size:18px;margin-bottom:16px;display:flex;align-items:center;gap:8px}}
.tabs{{display:flex;gap:0;margin-bottom:16px;border-bottom:1px solid #333}}
.tab{{padding:8px 16px;cursor:pointer;font-size:13px;color:#888;border-bottom:2px solid transparent;transition:.15s}}
.tab.on{{color:#6366f1;border-bottom-color:#6366f1}}
.tab:hover{{color:#ccc}}
.panel{{display:none}}.panel.show{{display:block}}
.card{{background:#1a1a1a;border:1px solid #282828;border-radius:8px;padding:12px;margin-bottom:10px}}
.card-title{{font-size:13px;font-weight:600;margin-bottom:10px;display:flex;align-items:center;gap:6px}}
.row{{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;gap:8px}}
.row:last-child{{margin-bottom:0}}
.row label{{font-size:12px;color:#888;min-width:70px;flex-shrink:0}}
.row .val{{font-size:12px;font-weight:600}}
.on{{color:#22c55e}}.off{{color:#ef4444}}
select,input[type=text],input[type=number],input[type=password]{{padding:5px 8px;border-radius:6px;border:1px solid #333;background:#222;color:#eee;font-size:12px;outline:none;width:100%}}
select:focus,input:focus{{border-color:#6366f1}}
select{{max-width:220px}}
.field{{margin-bottom:8px}}
.field label{{display:block;font-size:11px;color:#888;margin-bottom:3px}}
.btn{{background:#6366f1;color:#fff;border:none;border-radius:6px;padding:8px 16px;font-size:12px;cursor:pointer;font-weight:500;width:100%;margin-top:8px;transition:.15s}}
.btn:hover{{background:#4f46e5}}
.btn-sm{{padding:5px 12px;width:auto}}
.btn-outline{{background:transparent;border:1px solid #333;color:#888}}
.btn-outline:hover{{border-color:#6366f1;color:#6366f1}}
.toast{{position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:#6366f1;color:#fff;padding:8px 20px;border-radius:16px;font-size:12px;opacity:0;transition:opacity .3s;z-index:100;pointer-events:none}}
.toast.show{{opacity:1}}.toast.err{{background:#ef4444}}
.info-link{{font-size:11px;color:#6366f1;text-decoration:none}}
.info-link:hover{{text-decoration:underline}}
hr{{border:none;border-top:1px solid #282828;margin:12px 0}}
</style></head>
<body>
<h1>🎬 AI 弹幕助手</h1>
<div class="tabs">
  <div class="tab on" data-tab="status">📊 状态</div>
  <div class="tab" data-tab="settings">⚙️ 设置</div>
</div>

<div class="panel show" id="panel-status">
  <div class="card">
    <div class="card-title">📡 运行状态</div>
    <div class="row"><label>引擎</label><span class="val {'on' if running else 'off'}">{'运行中' if running else '已停止'}</span></div>
    <div class="row"><label>风格</label><span class="val">{style}</span></div>
    <div class="row"><label>语音</label><span class="val {'on' if voice_on else 'off'}">{'开启' if voice_on else '关闭'}</span></div>
    <div class="row"><label>文件源</label><span class="val {'on' if file_on else 'off'}">{'开启' if file_on else '关闭'}</span></div>
    <div class="row"><label>弹幕总数</label><span class="val">{len(history)}</span></div>
    <div class="row"><label>密度</label><span class="val">{density:.1f} 条/分</span></div>
    <div class="row"><label>运行时间</label><span class="val">{int(elapsed//60)}分{int(elapsed%60)}秒</span></div>
  </div>
  <div class="card">
    <div class="card-title">🔗 API 端点</div>
    <div style="font-size:12px;line-height:2">
      <a class="info-link" href="/status">GET /status</a> ·
      <a class="info-link" href="/stats">GET /stats</a> ·
      <a class="info-link" href="/logs">GET /logs</a> ·
      <a class="info-link" href="/styles">GET /styles</a>
    </div>
  </div>
</div>

<div class="panel" id="panel-settings">
  <div class="card">
    <div class="card-title">📷 视觉模型</div>
    <div class="field"><label>Base URL</label><input type="text" id="visionUrl" value="{vision_cfg.get('base_url', '')}"></div>
    <div class="field"><label>API Key</label><input type="password" id="visionKey" value=""></div>
    <div class="field"><label>模型名</label><input type="text" id="visionModel" value="{vision_cfg.get('model', '')}"></div>
  </div>

  <div class="card">
    <div class="card-title">🎤 语音弹幕</div>
    <div class="row"><label>启用</label><select id="voiceEnabled"><option value="true"{' selected' if voice_cfg.get('enabled', True) else ''}>开启</option><option value="false"{' selected' if not voice_cfg.get('enabled', True) else ''}>关闭</option></select></div>
    <div class="field"><label>ASR Base URL</label><input type="text" id="asrUrl" value="{asr_cfg.get('base_url', '')}"></div>
    <div class="field"><label>ASR API Key</label><input type="password" id="asrKey" value=""></div>
    <div class="field"><label>ASR 模型</label><input type="text" id="asrModel" value="{asr_cfg.get('model', 'FunAudioLLM/SenseVoiceSmall')}"></div>
  </div>

  <div class="card">
    <div class="card-title">🎯 弹幕行为</div>
    <div class="row"><label>风格</label><select id="danmuStyle">{style_options}</select></div>
    <div class="row"><label>间隔(秒)</label><input type="number" id="interval" value="{config.get('capture', {}).get('interval', 8)}" min="1" max="300" style="width:60px"></div>
  </div>

  <div class="card">
    <div class="card-title">💤 空闲暂停</div>
    <div class="row"><label>超时(秒)</label><input type="number" id="idleThreshold" value="{idle_threshold}" min="60" max="7200" style="width:80px"></div>
  </div>

  <button class="btn" id="btnSave">💾 保存设置</button>
  <div style="display:flex;gap:6px;margin-top:6px">
    <button class="btn btn-outline btn-sm" id="btnToggle" style="flex:1">{'⏸ 暂停引擎' if running else '▶ 启动引擎'}</button>
    <button class="btn btn-outline btn-sm" id="btnRestart" style="flex:1">🔄 重启</button>
  </div>
</div>

<script>
// Tab 切换
document.querySelectorAll('.tab').forEach(function(t){{
  t.addEventListener('click', function(){{
    document.querySelectorAll('.tab').forEach(function(x){{x.classList.remove('on')}});
    document.querySelectorAll('.panel').forEach(function(x){{x.classList.remove('show')}});
    this.classList.add('on');
    document.getElementById('panel-' + this.dataset.tab).classList.add('show');
  }});
}});

function toast(msg, err){{
  var el = document.createElement('div');
  el.className = 'toast' + (err ? ' err' : '');
  el.textContent = msg;
  document.body.appendChild(el);
  requestAnimationFrame(function(){{el.classList.add('show')}});
  setTimeout(function(){{el.remove()}}, 2500);
}}

// 保存设置
document.getElementById('btnSave').addEventListener('click', async function(){{
  this.textContent = '⏳ 保存中...';
  try {{
    var body = {{}};
    // 视觉模型
    var vUrl = document.getElementById('visionUrl').value.trim();
    var vKey = document.getElementById('visionKey').value.trim();
    var vModel = document.getElementById('visionModel').value.trim();
    if (vUrl) body['vision_api.base_url'] = vUrl;
    if (vKey) body['vision_api.api_key'] = vKey;
    if (vModel) body['vision_api.model'] = vModel;
    // 语音
    body['voice.enabled'] = document.getElementById('voiceEnabled').value === 'true';
    var aUrl = document.getElementById('asrUrl').value.trim();
    var aKey = document.getElementById('asrKey').value.trim();
    var aModel = document.getElementById('asrModel').value.trim();
    if (aUrl) body['voice.asr_api.base_url'] = aUrl;
    if (aKey) body['voice.asr_api.api_key'] = aKey;
    if (aModel) body['voice.asr_api.model'] = aModel;
    // 弹幕行为
    body.danmu_ai_style = document.getElementById('danmuStyle').value;
    body.capture_interval = parseInt(document.getElementById('interval').value) || 8;
    // 空闲
    body.idleThreshold = parseInt(document.getElementById('idleThreshold').value) || 600;

    var resp = await fetch('/config/reload', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify(body),
    }});
    var data = await resp.json();
    toast(data.ok ? '✅ 设置已保存' : '❌ ' + (data.error || '保存失败'), !data.ok);
  }} catch(e) {{ toast('❌ ' + e.message, true); }}
  this.textContent = '💾 保存设置';
}});

// 开关引擎
document.getElementById('btnToggle').addEventListener('click', async function(){{
  var resp = await fetch('/toggle', {{method:'POST'}});
  var data = await resp.json();
  if (data.ok) location.reload();
}});
</script>
</body></html>"""
            body_bytes = html.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', len(body_bytes))
            self.end_headers()
            self.wfile.write(body_bytes)

        elif self.path == "/status":
            self._json({
                "running": ai.running if ai else False,
                "style": config.get("danmu_ai_style", "pi"),
                "voice_enabled": voice is not None and voice.running,
                "voice_paused": voice.paused if voice else False,
                "file_source_enabled": file_source is not None,
                "total_danmu": len(history),
                "idle_paused": _app_state["idle_paused"],
                "hana_mode": _app_state["hana_mode"],
            })

        elif self.path == "/stats":
            emotions = {"neutral": 0, "happy": 0, "excited": 0, "sad": 0, "angry": 0}
            words_counter = {}
            for h in history[-50:]:
                t = h["text"] if isinstance(h, dict) else h
                for word in COMMON_WORDS:
                    if word in t:
                        words_counter[word] = words_counter.get(word, 0) + 1
            words = sorted(words_counter.items(), key=lambda x: -x[1])[:10]
            elapsed = (datetime.now() - _app_state["start_time"]).total_seconds() if _app_state["start_time"] else 0
            density = len(history) / max(elapsed / 60, 1)
            self._json({
                "ok": True,
                "stats": {
                    "total_count": len(history),
                    "ai_count": sum(1 for h in history if h["source"] == "ai"),
                    "voice_count": sum(1 for h in history if h["source"] == "voice"),
                    "file_count": sum(1 for h in history if h["source"] == "file"),
                    "manual_count": sum(1 for h in history if h["source"] == "manual"),
                    "density_per_min": round(density, 2),
                    "elapsed_sec": int(elapsed),
                    "top_words": words,
                },
            })

        elif self.path.startswith("/logs"):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            limit = int(qs.get("limit", ["50"])[0])
            self._json({"ok": True, "logs": history[-limit:]})

        elif self.path == "/styles":
            from danmu_ai import DanmuAI
            self._json({"ok": True, "styles": DanmuAI.list_styles()})

        elif self.path == "/voice/status":
            self._json({
                "ok": True,
                "voice_enabled": voice is not None and voice.running,
                "voice_paused": voice.paused if voice else False,
                "engine_type": type(voice.engine).__name__ if voice and voice.engine else None,
            })

        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        ai = _app_state["ai"]
        voice = _app_state["voice"]
        config = _app_state["config"]
        add_danmu = _app_state["add_danmu"]
        body = self._read_body()

        if self.path == "/toggle":
            if ai:
                if ai.running:
                    ai.stop()
                    self._json({"ok": True, "running": False})
                else:
                    ai.start()
                    self._json({"ok": True, "running": True})
            else:
                self._json({"ok": False, "error": "AI 弹幕未初始化"})

        elif self.path == "/send":
            text = body.get("text", "")
            if text and add_danmu:
                add_danmu(text, source="manual")
                self._json({"ok": True})
            else:
                self._json({"ok": False, "error": "text required"}, 400)

        elif self.path == "/style":
            style = body.get("style", "")
            if ai:
                ok = ai.set_style(style)
                self._json({"ok": ok, "style": style})
            else:
                self._json({"ok": False, "error": "AI 弹幕未初始化"})

        elif self.path == "/config/reload":
            # 热更新配置（支持嵌套 key 如 vision_api.base_url）
            def set_nested(d, key, val):
                parts = key.split(".")
                for p in parts[:-1]:
                    if p not in d or not isinstance(d[p], dict):
                        d[p] = {}
                    d = d[p]
                d[parts[-1]] = val

            for k, v in body.items():
                if "." in k:
                    set_nested(config, k, v)
                elif k == "danmu_ai_style" and ai:
                    ai.set_style(v)
                    config[k] = v
                elif k == "capture_interval" and ai:
                    ai.interval = int(v)
                    config.setdefault("capture", {})["interval"] = int(v)
                elif k == "idleThreshold":
                    config["idle_threshold"] = int(v)
                    idle_m = _app_state["idle_monitor"]
                    if idle_m:
                        idle_m.update_threshold(int(v))
                elif k == "buddyData":
                    buddy = _app_state["buddy"]
                    if buddy:
                        buddy.update_buddies(v)
                else:
                    config[k] = v

            # 同步到伙伴弹幕源
            buddy = _app_state["buddy"]
            if buddy:
                buddy.update_config(body)
            self._json({"ok": True})

        elif self.path == "/voice/toggle":
            enabled = body.get("enabled", None)
            if voice:
                if enabled is None:
                    enabled = not voice.running
                if enabled and not voice.running:
                    voice.start()
                elif not enabled and voice.running:
                    voice.stop()
                self._json({"ok": True, "voice_enabled": voice.running})
            else:
                self._json({"ok": False, "error": "语音弹幕未初始化"})

        elif self.path == "/voice/pause":
            if voice:
                voice.pause()
                self._json({"ok": True, "paused": True})
            else:
                self._json({"ok": False, "error": "语音弹幕未初始化"})

        elif self.path == "/voice/resume":
            if voice:
                voice.resume()
                self._json({"ok": True, "paused": False})
            else:
                self._json({"ok": False, "error": "语音弹幕未初始化"})

        elif self.path == "/idle/pause":
            _app_state["idle_paused"] = True
            if ai:
                ai.stop()
            if voice:
                voice.pause()
            idle_monitor = _app_state["idle_monitor"]
            if idle_monitor:
                idle_monitor.paused = True
            logger.info("[idle] HTTP 触发空闲暂停")
            self._json({"ok": True, "idle_paused": True})

        elif self.path == "/idle/resume":
            _app_state["idle_paused"] = False
            if ai:
                ai.start()
            if voice:
                voice.resume()
            idle_monitor = _app_state["idle_monitor"]
            if idle_monitor:
                idle_monitor.paused = False
            logger.info("[idle] HTTP 触发恢复")
            self._json({"ok": True, "idle_paused": False})

        elif self.path == "/buddy/status":
            buddy = _app_state["buddy"]
            if buddy:
                with buddy._lock:
                    buddies_summary = {
                        bid: {"name": b.get("name", bid), "color": b.get("color", "#FFF")}
                        for bid, b in buddy.buddies.items()
                    }
                self._json({
                    "ok": True,
                    "buddies": buddies_summary,
                    "selected": buddy.selected_buddies,
                    "interval": buddy.interval,
                })
            else:
                self._json({"ok": False, "error": "伙伴弹幕未初始化"})

        else:
            self._json({"error": "not found"}, 404)


def start_http_server(port: int):
    """在 daemon 线程中启动 HTTP Server，不阻塞 Qt 主线程。"""
    server = HTTPServer(("127.0.0.1", port), DanmuHTTPHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"[http] 控制接口已启动: http://127.0.0.1:{port}")
    return server


def main():
    parser = argparse.ArgumentParser(description="AI 弹幕助手 v2.0")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--no-ai", action="store_true", help="禁用 AI 截屏弹幕")
    parser.add_argument("--no-file", action="store_true", help="禁用文件弹幕源")
    parser.add_argument("--port", type=int, default=18900, help="HTTP 控制端口 (默认 18900)")
    parser.add_argument("--hana-mode", action="store_true", help="Hana 插件模式 (静默启动，无统计面板)")
    parser.add_argument("--ws-port", type=int, default=8765, help="WebSocket 服务端口 (默认 8765)")
    args = parser.parse_args()

    config = load_config(args.config)
    app = QApplication(sys.argv)

    # === 弹幕浮层（全屏透明 + 鼠标穿透）===
    engine = DanmuEngine(3840, 1080, tracks=10)
    overlay = DanmuOverlay(engine)
    overlay.show_fullscreen()
    print('[main] 弹幕浮层已创建', flush=True)

    # === 统计面板（hana-mode 下跳过） ===
    panel = None
    if not args.hana_mode:
        panel = DanmuStatsPanel(api_port=args.port)
        panel.show()
        print('[main] 统计面板已创建', flush=True)

    # 线程安全队列
    stats_queue = Queue()

    history = []
    start_time = datetime.now()

    def record_danmu(text: str, source: str = "file"):
        """记录一条弹幕（统一数据结构）。"""
        history.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "text": text,
            "source": source,
        })

    def add_danmu(text: str, source: str = "file"):
        """通用添加弹幕 + 记录 + 更新统计。"""
        color = random.choice(COLOR_POOL)
        track = hash(text) % 3
        overlay.add_danmu(text, color, track)
        record_danmu(text, source)
        push_stats()
        logger.info(f'弹幕发射 [{source}]: "{text[:20]}" 轨道={track} 颜色={color}')

    def push_stats():
        """把统计数据推入队列（后台线程调用这个）。"""
        total = len(history)
        emotions = {
            "neutral": random.randint(1, 10),
            "happy": random.randint(1, 8),
            "excited": random.randint(1, 5),
        }
        words_counter = {}
        for h in history[-20:]:
            t = h["text"] if isinstance(h, dict) else h
            for word in COMMON_WORDS:
                if word in t:
                    words_counter[word] = words_counter.get(word, 0) + 1
        words = sorted(words_counter.items(), key=lambda x: -x[1])[:5]
        stats_queue.put((total, emotions, words))

    def _drain_stats():
        """主线程定时调用：从队列取数据并更新面板。"""
        if not panel:
            return
        drained = []
        while not stats_queue.empty():
            drained.append(stats_queue.get_nowait())
        for total, emotions, words in drained:
            panel.update_data(total, emotions, words)

    stats_timer = QTimer()
    stats_timer.timeout.connect(_drain_stats)
    stats_timer.start(200)

    # === AI 截屏弹幕 ===
    ai = None
    if not args.no_ai:
        ai = DanmuAI(overlay, config, interval=6.0, on_danmu=lambda text, source: add_danmu(text, source))
        ai.start()
        print('[main] AI 截屏弹幕已启动', flush=True)

    # === 文件弹幕源 ===
    file_source = None
    if not args.no_file:
        danmu_file = config.get("danmu_source", "danmu_source.txt")
        file_source = DanmuFileSource(danmu_file)
        file_source.on_danmu(lambda text: add_danmu(text))
        file_source.start()
        print(f'[main] 文件弹幕源已启动: {Path(danmu_file).absolute()}', flush=True)

    # === 语音理解弹幕 ===
    voice = None
    voice_result_queue = queue.Queue(maxsize=10)
    voice_ai_result_queue = queue.Queue(maxsize=10)  # AI生成结果回主线程

    if config.get("voice", {}).get("enabled", True):
        voice = VoiceDanmu(overlay, config)
        def on_voice_recognized(text: str):
            try:
                voice_result_queue.put_nowait(text)
            except queue.Full:
                pass
        voice.on_danmu = on_voice_recognized
        voice.start()
        print('[main] 语音理解弹幕已启动', flush=True)

    # 主线程定时器：处理语音识别结果
    from concurrent.futures import ThreadPoolExecutor
    voice_executor = ThreadPoolExecutor(max_workers=2)

    def _process_voice_results():
        # 先处理识别结果（提交AI生成）
        while not voice_result_queue.empty():
            try:
                text = voice_result_queue.get_nowait()
            except queue.Empty:
                break
            if ai:
                future = voice_executor.submit(ai.generate_from_voice, text)
                def _on_done(fut, t=text):
                    try:
                        danmu_text = fut.result(timeout=15)
                    except Exception as e:
                        print(f'[voice] AI 生成失败: {e}', flush=True)
                        danmu_text = ""
                    if danmu_text:
                        try:
                            voice_ai_result_queue.put_nowait(danmu_text)
                        except queue.Full:
                            pass
                future.add_done_callback(_on_done)
        # 再处理AI生成结果（主线程发射弹幕）
        count = 0
        while not voice_ai_result_queue.empty():
            try:
                danmu_text = voice_ai_result_queue.get_nowait()
            except queue.Empty:
                break
            count += 1
            add_danmu(danmu_text, "voice")
        if count:
            print(f'[main] 语音弹幕发射 {count} 条', flush=True)

    voice_timer = QTimer()
    voice_timer.timeout.connect(_process_voice_results)
    voice_timer.start(200)

    # === 伙伴弹幕 ===
    buddy = BuddyDanmuSource({
        "buddy_interval": config.get("buddy_interval", 90),
        "buddy_interval_min": config.get("buddy_interval_min", 60),
        "buddy_interval_max": config.get("buddy_interval_max", 180),
        "buddy_interval_mode": config.get("buddy_interval_mode", "fixed"),
        "buddy_memory_ratio": config.get("buddy_memory_ratio", 30),
        "selected_buddies": config.get("selected_buddies", []),
        "buddy_nicknames": config.get("buddy_nicknames", []),
        "user_name": config.get("user_name", ""),
        "vision_api": config.get("vision_api", {}),
    })
    buddy_data = config.get("buddyData", {})
    if buddy_data:
        buddy.update_buddies(buddy_data)
    buddy.on_danmu = lambda text, color, bid: add_danmu(text, source=f"buddy:{bid}")
    buddy.start()
    print('[main] 伙伴弹幕已启动', flush=True)

    # === B站直播弹幕 ===
    blivedm = None
    blivedm_cfg = config.get("blivedm", {})
    if blivedm_cfg.get("enabled", False):
        room_id = blivedm_cfg.get("room_id")
        if room_id:
            blivedm = BiliLiveClient(
                room_id=room_id,
                cookie=blivedm_cfg.get("cookie") or None,
                uid=blivedm_cfg.get("uid", 0),
                heartbeat_interval=blivedm_cfg.get("heartbeat_interval", 30.0),
                on_danmu=lambda text, source="blivedm", user=None: add_danmu(text, source=source),
            )
            blivedm.start()
            print(f'[main] B站直播弹幕已启动 (房间 {room_id})', flush=True)
        else:
            print('[main] blivedm.enabled 但缺少 room_id，已跳过', flush=True)

    # === 空闲暂停 ===
    idle_monitor = IdleMonitor(threshold_sec=config.get("idle_threshold", 600))
    def _on_idle_pause():
        if ai: ai.stop()
        if voice: voice.pause()
        _app_state["idle_paused"] = True
    def _on_idle_resume():
        if ai: ai.start()
        if voice: voice.resume()
        _app_state["idle_paused"] = False
    idle_monitor.on_pause = _on_idle_pause
    idle_monitor.on_resume = _on_idle_resume
    idle_monitor.start()
    print(f'[main] 空闲监测已启动 ({config.get("idle_threshold", 600)}s)', flush=True)

    # === 填充共享状态 ===
    _app_state.update({
        "ai": ai,
        "voice": voice,
        "file_source": file_source,
        "buddy": buddy,
        "blivedm": blivedm,
        "idle_monitor": idle_monitor,
        "overlay": overlay,
        "engine": engine,
        "config": config,
        "history": history,
        "add_danmu": add_danmu,
        "hana_mode": args.hana_mode,
        "start_time": start_time,
    })

    # === HTTP 控制接口 ===
    http_server = start_http_server(args.port)

    # === Phase 4 WebSocket 服务 ===
    ws = WSServer(port=args.ws_port, app_state=_app_state)
    ws.start()
    print(f"[ws] WebSocket 服务已启动: ws://127.0.0.1:{args.ws_port}")

    # === 启动信息 ===
    mode_str = " [Hana 插件模式]" if args.hana_mode else ""
    print("=" * 60)
    print(f"  AI 弹幕助手 v2.0{mode_str}")
    print("=" * 60)
    print(f"  AI 截屏弹幕: {'开启' if ai else '关闭'}")
    print(f"  语音理解弹幕: {'开启' if voice else '关闭'}")
    print(f"  文件弹幕源: {'开启' if file_source else '关闭'}")
    print(f"  伙伴弹幕: 开启")
    print(f"  空闲监测: 开启 ({config.get('idle_threshold', 600)}s)")
    print(f"  浮层: 全屏透明 + 鼠标穿透 + 顶部 30% 区域")
    print(f"  HTTP 控制: http://127.0.0.1:{args.port}")
    print("=" * 60)
    if file_source:
        print(f"  往 {Path(danmu_file).absolute()} 写文字 → 弹幕")
    if ai:
        print(f"  每 8 秒截屏 → AI 分析 → 生成弹幕")
    if voice:
        print(f"  麦克风收音 → Whisper 识别 → AI 理解 → 互动弹幕")
    print("=" * 60)

    # === 退出时保存统计 ===
    def save_stats():
        end_time = datetime.now()
        duration = end_time - start_time
        stats_dir = Path("stats")
        stats_dir.mkdir(exist_ok=True)
        stats_path = stats_dir / f"danmu_stats_{start_time.strftime('%Y%m%d_%H%M%S')}.txt"
        with open(stats_path, 'w', encoding='utf-8') as f:
            f.write(f"=== AI 弹幕助手 会话统计 ===\n")
            f.write(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"持续时间: {int(duration.total_seconds())} 秒\n")
            f.write(f"总弹幕数: {len(history)}\n")
            f.write(f"AI 截屏弹幕: {sum(1 for h in history if h['source'] == 'ai')}\n")
            f.write(f"语音理解弹幕: {sum(1 for h in history if h['source'] == 'voice')}\n")
            f.write(f"文件弹幕: {sum(1 for h in history if h['source'] == 'file')}\n")
            f.write(f"手动弹幕: {sum(1 for h in history if h['source'] == 'manual')}\n")
            f.write(f"伙伴弹幕: {sum(1 for h in history if h['source'].startswith('buddy'))}\n")
            f.write("=" * 40 + "\n\n")
            f.write("=== 弹幕列表 ===\n")
            for i, h in enumerate(history, 1):
                f.write(f"{i}. [{h['source']}] [{h['time']}] {h['text']}\n")
        print(f'\n[stats] 统计已保存: {stats_path.absolute()}', flush=True)

    app.aboutToQuit.connect(save_stats)

    def _on_sigint(sig, frame):
        print("\n[signal] 收到退出信号", flush=True)
        if ai: ai.stop()
        if voice: voice.stop()
        if file_source: file_source.stop()
        buddy.stop()
        idle_monitor.stop()
        overlay.stop()
        app.quit()

    signal.signal(signal.SIGINT, _on_sigint)

    try:
        sys.exit(app.exec())
    except BaseException as e:
        print(f"\n[exit] 异常: {e}", flush=True)
        if ai: ai.stop()
        if voice: voice.stop()
        if file_source: file_source.stop()
        buddy.stop()
        idle_monitor.stop()
        overlay.stop()
        app.quit()
        raise


if __name__ == "__main__":
    main()
