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
import threading
import queue
from queue import Queue
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from danmu_stats_panel import DanmuStatsPanel
from danmu_overlay_full import DanmuOverlay, DanmuEngine
from danmu_file_source import DanmuFileSource
from danmu_ai import DanmuAI
from voice_danmu import VoiceDanmu

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


def main():
    parser = argparse.ArgumentParser(description="AI 弹幕助手 v2.0")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--no-ai", action="store_true", help="禁用 AI 截屏弹幕")
    parser.add_argument("--no-file", action="store_true", help="禁用文件弹幕源")
    args = parser.parse_args()

    config = load_config(args.config)
    app = QApplication(sys.argv)

    # === 弹幕浮层（全屏透明 + 鼠标穿透）===
    engine = DanmuEngine(3840, 1080, tracks=10)
    overlay = DanmuOverlay(engine)
    overlay.show_fullscreen()
    print('[main] 弹幕浮层已创建', flush=True)

    # === 统计面板 ===
    panel = DanmuStatsPanel()
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

    # === 启动信息 ===
    print("=" * 60)
    print("  AI 弹幕助手 v2.0")
    print("=" * 60)
    print(f"  AI 截屏弹幕: {'开启' if ai else '关闭'}")
    print(f"  语音理解弹幕: {'开启' if voice else '关闭'}")
    print(f"  文件弹幕源: {'开启' if file_source else '关闭'}")
    print(f"  浮层: 全屏透明 + 鼠标穿透 + 顶部 30% 区域")
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
            f.write("=" * 40 + "\n\n")
            f.write("=== 弹幕列表 ===\n")
            for i, h in enumerate(history, 1):
                f.write(f"{i}. [{h['source']}] [{h['time']}] {h['text']}\n")
        print(f'\n[stats] 统计已保存: {stats_path.absolute()}', flush=True)

    app.aboutToQuit.connect(save_stats)

    def _on_sigint(sig, frame):
        print("\n[signal] 收到退出信号", flush=True)
        if ai:
            ai.stop()
        if voice:
            voice.stop()
        if file_source:
            file_source.stop()
        overlay.stop()
        app.quit()

    signal.signal(signal.SIGINT, _on_sigint)

    try:
        sys.exit(app.exec())
    except BaseException as e:
        print(f"\n[exit] 异常: {e}", flush=True)
        if ai:
            ai.stop()
        if voice:
            voice.stop()
        if file_source:
            file_source.stop()
        overlay.stop()
        app.quit()
        raise


if __name__ == "__main__":
    main()
