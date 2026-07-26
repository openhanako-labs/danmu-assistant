"""
伙伴弹幕源 — 根据屏幕内容 + 伙伴性格 + 好感度生成个性化弹幕
从 Hana 插件层接收伙伴数据（闲不住的好感度/体力/心情），
结合当前屏幕描述，让每个助手以自己的性格发弹幕。
"""
import time
import random
import threading
import logging
import json
import urllib.request

logger = logging.getLogger("buddy")


class BuddyDanmuSource:
    """伙伴弹幕生成器。"""

    AFFECTION称呼 = {0: "你", 5: "你", 10: "你", 15: "主人", 20: "亲爱的"}

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.buddies = {}
        self.running = False
        self._thread = None
        self._lock = threading.Lock()

        # 回调
        self.on_danmu = None       # (text, color, buddy_id)
        self.get_screen_desc = None  # () -> str

        # 配置
        self.interval = self.config.get("buddy_interval", 90)
        self.interval_min = self.config.get("buddy_interval_min", 60)
        self.interval_max = self.config.get("buddy_interval_max", 180)
        self.memory_ratio = self.config.get("buddy_memory_ratio", 30)
        self.selected_buddies = self.config.get("selected_buddies", [])
        self.nickname_pool = self.config.get("buddy_nicknames", [])
        self.user_name = self.config.get("user_name", "")

    def update_buddies(self, buddy_data: dict):
        with self._lock:
            self.buddies = buddy_data or {}
        logger.info(f"[buddy] 伙伴数据已更新: {list(self.buddies.keys())}")

    def update_config(self, config: dict):
        for key in ("buddy_interval", "buddy_interval_min", "buddy_interval_max",
                     "buddy_memory_ratio", "selected_buddies", "buddy_nicknames", "user_name"):
            if key in config:
                setattr(self, key, config[key])

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("[buddy] 伙伴弹幕已启动")

    def stop(self):
        self.running = False

    def _loop(self):
        while self.running:
            try:
                if self.config.get("buddy_interval_mode") == "random":
                    interval = random.uniform(self.interval_min, self.interval_max)
                else:
                    interval = self.interval
                time.sleep(interval)
                if not self.running:
                    break
                self._generate_round()
            except Exception as e:
                logger.error(f"[buddy] 错误: {e}")
                time.sleep(10)

    def _generate_round(self):
        with self._lock:
            buddies = dict(self.buddies)
            selected = list(self.selected_buddies)
        if not buddies:
            return

        screen_desc = ""
        if self.get_screen_desc:
            try:
                screen_desc = self.get_screen_desc() or ""
            except Exception:
                pass

        for buddy_id, buddy in buddies.items():
            if selected and buddy_id not in selected:
                continue
            if random.random() > self._calc_probability(buddy):
                continue

            use_memory = random.random() * 100 < self.memory_ratio
            text = self._generate_danmu(buddy, screen_desc, use_memory)
            if not text:
                continue
            text = self._apply_nickname(text, buddy)

            color = buddy.get("color", "#FFFFFF")
            if self.on_danmu:
                self.on_danmu(text, color, buddy_id)
                logger.info(f'[buddy] {buddy.get("name", buddy_id)}: "{text}"')
            time.sleep(random.uniform(0.5, 2.0))

    def _calc_probability(self, buddy: dict) -> float:
        base = 0.3
        affection_bonus = buddy.get("affection", 0) * 0.01
        mood_bonus = (buddy.get("mood", 50) - 50) * 0.005
        energy_factor = max(buddy.get("energy", 80) / 100, 0.3)
        return min(max((base + affection_bonus + mood_bonus) * energy_factor, 0.05), 0.9)

    def _generate_danmu(self, buddy: dict, screen_desc: str, use_memory: bool) -> str:
        name = buddy.get("name", "伙伴")
        style_desc = buddy.get("styleDesc", "")
        mood = buddy.get("mood", 50)
        energy = buddy.get("energy", 80)
        affection = buddy.get("affection", 0)
        narrative = buddy.get("narrative", "")

        prompt_parts = [f"你是{name}。"]
        if style_desc:
            prompt_parts.append(f"你的性格：{style_desc[:200]}")

        mood_desc = "心情很好" if mood >= 70 else "心情不错" if mood >= 50 else "心情有点低落" if mood >= 30 else "心情很差"
        energy_desc = "精力充沛" if energy >= 60 else "有点累了" if energy >= 30 else "很疲惫"
        prompt_parts.append(f"你现在{mood_desc}，{energy_desc}。")

        if affection >= 15:
            prompt_parts.append(f"你和用户关系很好（好感度{affection}），可以亲密一些。")
        elif affection >= 8:
            prompt_parts.append(f"你和用户比较熟（好感度{affection}），语气自然。")
        else:
            prompt_parts.append(f"你和用户还不太熟（好感度{affection}），保持礼貌。")

        if use_memory and narrative:
            prompt_parts.append(f"你最近的状态：{narrative}")
            prompt_parts.append("根据你自己的状态，说一句自然的话（10-20字）。不要描述屏幕，而是说你自己的想法。")
        elif screen_desc:
            prompt_parts.append(f"用户当前屏幕内容：{screen_desc[:200]}")
            prompt_parts.append("根据屏幕内容，以你的性格说一句简短的话（10-20字）。")
        else:
            prompt_parts.append("随口说一句简短的话（10-20字），像是在旁边陪伴时说的。")

        prompt_parts.append("直接输出弹幕内容，不要解释，不要引号，不要换行。")

        try:
            text = self._call_api("\n".join(prompt_parts))
            if text:
                return text.strip()[:30]
        except Exception as e:
            logger.error(f"[buddy] API 调用失败: {e}")
        return ""

    def _apply_nickname(self, text: str, buddy: dict) -> str:
        if random.random() > 0.35:
            return text
        nick = random.choice(self.nickname_pool) if self.nickname_pool else self.user_name
        if not nick:
            return text
        if nick not in text:
            return f"{nick}，{text}"
        return text

    def _call_api(self, prompt: str) -> str:
        cfg = self.config.get("vision_api", {})
        base_url = cfg.get("base_url", "https://api.siliconflow.cn/v1")
        model = cfg.get("model", "Qwen/Qwen3.5-397B-A17B")
        api_key = cfg.get("api_key", "")
        if not api_key:
            return ""

        url = f"{base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 50,
            "temperature": 0.85,
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        lines = [l.strip() for l in content.split("\n") if l.strip()]
        return lines[0] if lines else ""
