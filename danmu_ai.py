"""
弹幕 AI 生成器 - 截屏 + 视觉模型分析
调用 siliconflow Qwen3.5-VL 分析画面，生成弹幕
"""
import time
import base64
import io
import threading
from pathlib import Path

import mss
from PIL import Image


class DanmuAI:
    """截屏 + AI 生成弹幕。"""

    # 预置弹幕池（API 超时/失败时 fallback）
    FALLBACK_DANMU = [
        "这画面有点东西",
        "操作变形了哈哈哈",
        "策划出来挨打",
        "这也能通关？",
        "满屏的UI，眼花缭乱",
        "游戏：你看我干嘛",
        "这什么阴间设计",
        "主播这波操作可以",
        "弹幕：我的评价是寄",
        "这BUG是feature吧",
        "规则系魔法师",
        "赛博炼丹现场",
        "AI：我也看傻了",
        "这关卡难度离谱",
        "手搓高达是吧",
    ]

    def __init__(self, overlay, config: dict, interval: float = 5.0, dedup_seconds: float = 60.0, on_danmu=None):
        self.overlay = overlay
        self.config = config
        self.interval = interval
        self.dedup_seconds = dedup_seconds
        self._recent: list = []
        self.running = False
        self._thread = None
        self.on_danmu = on_danmu
        self._last_frame_hash: str = ""  # 关键帧检测：上一帧的均值哈希
        self._frame_diff_threshold = 0.0  # 0=diff<0永远不成立=永远不跳过=真正固定截屏

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print('[ai] 截屏+AI 弹幕生成已启动', flush=True)

    def stop(self):
        self.running = False

    def _loop(self):
        while self.running:
            try:
                self._capture_and_generate()
            except Exception as e:
                print(f'[ai] 错误: {e}', flush=True)
            time.sleep(self.interval)

    def _capture_and_generate(self):
        with mss.mss() as sct:
            primary = next((m for m in sct.monitors if m.get('is_primary')), sct.monitors[1])
            screenshot = sct.grab(primary)
            img = Image.frombytes('RGB', screenshot.size, screenshot.rgb)

        # 关键帧检测：缩到 64x36 灰度，比较均值
        small = img.resize((64, 36), Image.Resampling.LANCZOS).convert('L')
        gray_mean = sum(small.getdata()) / len(small.getdata())
        diff = abs(gray_mean - self._last_frame_hash) if self._last_frame_hash else 999
        if diff < self._frame_diff_threshold:
            return  # 画面没变，跳过 API 调用
        self._last_frame_hash = gray_mean
        del small

        # 压缩到 640x360（减少 API 带宽）
        img.thumbnail((640, 360), Image.Resampling.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=60)
        b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        # 立即释放内存，不落盘
        del img, buf

        style = self.config.get("danmu_ai_style", "pi")
        recent_texts = [t for t, _ in self._recent[-10:]]
        prompt = self._get_prompt_by_style(style, recent_texts)

        # 重试机制（带退避）
        danmu_list = []
        for attempt in range(2):
            try:
                danmu_list = self._call_vision_api(prompt, b64)
            except Exception as e:
                print(f'[ai] 第 {attempt+1} 次调用异常: {e}', flush=True)
            if danmu_list:
                break
            wait = min(2 ** attempt, 10) + 0.5
            print(f'[ai] 第 {attempt+1} 次调用失败，{wait:.1f}秒后重试...', flush=True)
            time.sleep(wait)

        # Fallback：API 完全失败时用预置弹幕池
        if not danmu_list:
            import random as _random
            fallback = _random.choice(self.FALLBACK_DANMU)
            danmu_list = [fallback]
            print(f'[ai] API 不可用，fallback 弹幕: {fallback}', flush=True)

        if danmu_list:
            now = time.time()
            self._recent = [(t, ts) for t, ts in self._recent if now - ts < self.dedup_seconds]

            valid = []
            for text in danmu_list:
                if any(t == text for t, _ in self._recent):
                    continue
                if self._is_similar(text, self._recent):
                    continue
                self._recent.append((text, now))
                valid.append(text)

            for i, text in enumerate(valid):
                time.sleep(0.6)
                # 只通过回调发射，避免双份
                if self.on_danmu:
                    self.on_danmu(text, source="ai")
            if valid:
                print(f'[ai] 逐条发送: {valid}', flush=True)

    def _get_prompt_by_style(self, style: str, recent_danmu: list = None) -> str:
        base = """你是一个游戏弹幕生成专家。请按以下步骤分析这张截图：

【第一步：场景诊断】
- 场景类型：战斗/探索/对话/解谜/剧情/菜单/其他
- 核心元素：看到了什么角色/物体/文字/UI
- 当前情绪：紧张/搞笑/感动/无聊/燃/虐/离谱
- 情绪强度：高/中/低

【第二步：弹幕策略】
根据场景类型和情绪强度，选择弹幕角度：
- 战斗/紧张 → 吐槽操作、喊技能名、吐槽难度
- 探索/轻松 → 吐槽 scenery、玩梗、感叹风景
- 对话/剧情 → 吐槽台词、吐槽角色、玩梗
- 解谜/卡关 → 吐槽设计、求助、吐槽自己
- 菜单/无聊 → 吐槽 UI、玩梗、吐槽等待

【第三步：生成弹幕】
基于以上分析，生成 2-3 条 B 站风格弹幕。要求：
- 每条 5-15 字，用中文
- 强相关画面内容，禁止空泛
- 风格：吐槽、夸奖、玩梗、惊讶 混合
- 像真人发的，不要 AI 腔

【输出格式（严格遵循）】
直接输出弹幕内容，每行一条。
禁止输出：解释、序号、标点包裹、引号、分析过程、总结。
示例输出：
这BOSS血条是假的吧
操作变形了哈哈哈
这剧情刀我"""

        avoid = ""
        if recent_danmu:
            avoid = f"\n\n最近已发的弹幕（绝对不要重复或相似）：{', '.join(recent_danmu[-8:])}"

        styles = {
            "pi": "风格要皮、要玩梗、要吐槽，像懂行的朋友在聊天。" + avoid,
            "normal": "风格自然随意，像普通观众在发表感想。" + avoid,
            "serious": "风格正经一些，少玩梗，多描述画面内容。" + avoid,
        }
        return base + styles.get(style, styles["pi"])

    def _is_similar(self, text: str, recent: list) -> bool:
        """检查 text 是否和 recent 里的任意一条重复或高度相似。"""
        for t, _ in recent:
            # 完全相等
            if text == t:
                return True
            # 互相包含（短句被长句包含也算重复）
            if text in t or t in text:
                return True
            # 前3字相同（防止"这个游戏太难了"和"这个游戏太难了吧"都发出来）
            if len(text) >= 3 and len(t) >= 3 and text[:3] == t[:3]:
                return True
        return False

    def _call_vision_api(self, prompt: str, image_b64: str) -> list:
        try:
            import urllib.request
            import json

            cfg = self.config.get("vision_api", {})
            provider = cfg.get("provider", "siliconflow")
            base_url = cfg.get("base_url", "https://api.siliconflow.cn/v1")
            model = cfg.get("model", "Qwen/Qwen3.5-397B-A17B")
            api_key = cfg.get("api_key", "")

            url = f"{base_url}/chat/completions"

            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_b64}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 200,
                "temperature": 0.8,
            }

            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode('utf-8'),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode('utf-8'))

            content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            lines = [l.strip() for l in content.split('\n') if l.strip() and not l.strip().startswith('#')]
            return lines[:5]

        except Exception as e:
            print(f'[ai] API 调用失败: {e}', flush=True)
            return []

    def generate_from_voice(self, text: str) -> str:
        try:
            b64 = self._capture_screen_b64(max_size=(640, 360), quality=60)

            prompt = f"""玩家刚才说了一句话：「{text}」
结合当前游戏画面，生成一条 B 站风格的弹幕回复。
要求：
- 简短（5-15 字）
- 要和玩家说的话形成互动或吐槽
- 风格可以皮、可以玩梗
- 用中文
直接输出弹幕内容，不要编号不要解释。"""

            result = self._call_vision_api(prompt, b64)
            if result:
                return result[0]
            return ""
        except Exception as e:
            print(f'[voice-ai] 生成失败: {e}', flush=True)
            return ""

    def _capture_screen_b64(self, max_size=(640, 360), quality=60) -> str:
        """截屏 → 压缩 → base64。复用于 AI 截屏弹幕和语音弹幕。"""
        import mss
        from PIL import Image
        with mss.mss() as sct:
            primary = next((m for m in sct.monitors if m.get('is_primary')), sct.monitors[1])
            screenshot = sct.grab(primary)
            img = Image.frombytes('RGB', screenshot.size, screenshot.rgb)
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        buf = __import__('io').BytesIO()
        img.save(buf, format='JPEG', quality=quality)
        b64 = __import__('base64').b64encode(buf.getvalue()).decode('utf-8')
        # 立即释放内存
        del img, buf
        return b64


if __name__ == "__main__":
    from danmu_overlay_pyqt import DanmuOverlay, DanmuEngine
    from PyQt6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    engine = DanmuEngine(800, 150, tracks=3)
    overlay = DanmuOverlay(engine)
    overlay.show_for_screen(0, 0)

    ai = DanmuAI(overlay, {}, interval=8.0)
    ai.start()

    sys.exit(app.exec())
