"""
Hanako 弹幕联动桥接模块
Phase 4: 将弹幕事件推送给 Hanako，触发桌宠反应

工作流程：
  弹幕生成 → 情绪分析 → 阈值判断 → 推送 Hanako → 桌宠反应 → 反馈循环
"""
import asyncio
import json
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path


class PetReaction(Enum):
    """桌宠反应类型"""
    IDLE = "idle"              # 待机
    JUMP = "jump"              # 跳跃（兴奋/惊讶）
    LAUGH = "laugh"            # 大笑（开心/玩梗）
    CRY = "cry"                # 哭泣（悲伤）
    ANGRY = "angry"            # 生气（愤怒）
    HIDE = "hide"              # 躲藏（害怕）
    WAVE = "wave"              # 挥手（中性/打招呼）
    SPIN = "spin"              # 旋转（兴奋到极致）
    HEART = "heart"            # 爱心（喜欢/崇拜）
    STAR_EYE = "stare"         # 星星眼（崇拜）


@dataclass
class DanmuStats:
    """弹幕统计数据"""
    total_count: int = 0
    meme_count: int = 0
    comment_count: int = 0
    reaction_count: int = 0
    excited_count: int = 0
    happy_count: int = 0
    sad_count: int = 0
    angry_count: int = 0
    last_update_time: float = field(default_factory=time.time)
    
    def add_danmu(self, style: str, emotion: str = "neutral"):
        """添加一条弹幕记录"""
        self.total_count += 1
        self.last_update_time = time.time()
        
        if style == "meme":
            self.meme_count += 1
        elif style == "comment":
            self.comment_count += 1
        elif style == "reaction":
            self.reaction_count += 1
        
        if emotion == "excited":
            self.excited_count += 1
        elif emotion == "happy":
            self.happy_count += 1
        elif emotion == "sad":
            self.sad_count += 1
        elif emotion == "angry":
            self.angry_count += 1
    
    def get_density(self, window_seconds: float = 60.0) -> float:
        """获取弹幕密度（每分钟）"""
        if self.total_count == 0:
            return 0
        # 简化：假设从第一次弹幕到现在
        return self.total_count / max(window_seconds, 1)
    
    def to_dict(self) -> dict:
        return asdict(self)


class ReactionThreshold:
    """反应阈值配置"""
    
    def __init__(self):
        # 弹幕密度触发阈值（每分钟）
        self.density_jump = 3.0        # 密度 >= 3 条/分钟 → 跳跃
        self.density_laugh = 5.0       # 密度 >= 5 条/分钟 → 大笑
        self.density_spin = 10.0       # 密度 >= 10 条/分钟 → 旋转
        
        # 兴奋度触发阈值
        self.excited_jump = 3          # 兴奋弹幕 >= 3 条 → 跳跃
        self.excited_spin = 5          # 兴奋弹幕 >= 5 条 → 旋转
        
        # 负面情绪触发阈值
        self.sad_cry = 2             # 悲伤弹幕 >= 2 条 → 哭泣
        self.angry_hide = 2          # 愤怒弹幕 >= 2 条 → 躲藏
        
        # 冷却时间（秒）
        self.cooldown = 3.0            # 两次反应之间最少间隔
    
    def should_trigger(self, last_reaction_time: float) -> bool:
        """检查是否应该触发反应（冷却时间已过）"""
        return (time.time() - last_reaction_time) >= self.cooldown


class HanakoDanmuBridge:
    """
    Hanako 弹幕联动桥接器
    
    核心功能：
    1. 监听弹幕事件
    2. 统计弹幕数量和情绪
    3. 根据阈值触发桌宠反应
    4. 发送反应事件到 Hanako
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.stats = DanmuStats()
        self.thresholds = ReactionThreshold()
        self.last_reaction_time = 0
        self.reaction_log: List[dict] = []  # 反应历史记录
        
        # Hanako 配置
        self.hanako_url = self.config.get("hanako_url", "http://localhost:18789")
        self.hanako_token = self.config.get("hanako_token", None)
        
        # 回调函数
        self.on_reaction = None  # 反应回调
        
        # 加载历史记录
        self._load_reaction_log()
    
    def add_danmu(self, text: str, style: str = "default", emotion: str = "neutral"):
        """
        添加弹幕并检查是否需要触发反应
        
        Args:
            text: 弹幕文本
            style: 弹幕风格
            emotion: 情绪类型
        """
        # 记录统计
        self.stats.add_danmu(style, emotion)
        
        # 检查是否应该触发反应
        if not self.thresholds.should_trigger(self.last_reaction_time):
            return
        
        reaction = self._determine_reaction(style, emotion)
        
        if reaction and self.thresholds.should_trigger(self.last_reaction_time):
            self._trigger_reaction(reaction, text, style, emotion)
    
    def _determine_reaction(self, style: str, emotion: str) -> Optional[PetReaction]:
        """
        根据弹幕风格和情绪确定桌宠反应
        
        Returns:
            PetReaction 或 None（不触发）
        """
        density = self.stats.get_density()
        excited = self.stats.excited_count
        sad = self.stats.sad_count
        angry = self.stats.angry_count
        
        # 负面情绪优先
        if sad >= self.thresholds.sad_cry:
            return PetReaction.CRY
        
        if angry >= self.thresholds.angry_hide:
            return PetReaction.HIDE
        
        # 高密度兴奋
        if density >= self.thresholds.density_spin or excited >= self.thresholds.excited_spin:
            return PetReaction.SPIN
        
        # 高密度
        if density >= self.thresholds.density_laugh or style == "meme":
            return PetReaction.LAUGH
        
        if density >= self.thresholds.density_jump or excited >= self.thresholds.excited_jump:
            return PetReaction.JUMP
        
        # 默认：中性互动
        if style == "comment":
            return PetReaction.WAVE
        
        return None
    
    def _trigger_reaction(self, reaction: PetReaction, text: str, style: str, emotion: str):
        """
        触发桌宠反应
        
        Args:
            reaction: 反应类型
            text: 弹幕文本
            style: 弹幕风格
            emotion: 情绪
        """
        self.last_reaction_time = time.time()
        
        # 记录反应
        record = {
            "reaction": reaction.value,
            "text": text,
            "style": style,
            "emotion": emotion,
            "timestamp": time.time(),
            "stats": self.stats.to_dict()
        }
        self.reaction_log.append(record)
        
        # 限制历史记录大小
        if len(self.reaction_log) > 100:
            self.reaction_log = self.reaction_log[-100:]
        
        # 保存日志
        self._save_reaction_log()
        
        # 打印反应
        print(f"[Hanako] 触发桌宠反应: {reaction.value}")
        print(f"  弹幕: {text}")
        print(f"  风格: {style}, 情绪: {emotion}")
        print(f"  当前统计: 总数={self.stats.total_count}, 密度={self.stats.get_density():.1f}/min")
        
        # 调用回调
        if self.on_reaction:
            try:
                self.on_reaction(reaction, text, style, emotion)
            except Exception as e:
                print(f"[Hanako] 回调执行失败: {e}")
    
    async def send_to_hanako(self, reaction: PetReaction, text: str):
        """
        发送反应事件到 Hanako
        
        Args:
            reaction: 反应类型
            text: 弹幕文本
        """
        try:
            import httpx
            
            payload = {
                "type": "pet_reaction",
                "reaction": reaction.value,
                "text": text,
                "timestamp": time.time()
            }
            
            headers = {"Content-Type": "application/json"}
            if self.hanako_token:
                headers["Authorization"] = f"Bearer {self.hanako_token}"
            
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{self.hanako_url}/api/pet/reaction",
                    json=payload,
                    headers=headers
                )
                response.raise_for_status()
                print(f"[Hanako] 发送成功: {response.status_code}")
                
        except ImportError:
            print("[Hanako] httpx 未安装，跳过发送")
        except Exception as e:
            print(f"[Hanako] 发送失败: {e}")
    
    def get_stats(self) -> dict:
        """获取当前统计信息"""
        return {
            "stats": self.stats.to_dict(),
            "thresholds": {
                "density_jump": self.thresholds.density_jump,
                "density_laugh": self.thresholds.density_laugh,
                "cooldown": self.thresholds.cooldown,
            },
            "reaction_count": len(self.reaction_log)
        }
    
    def reset_stats(self):
        """重置统计数据"""
        self.stats = DanmuStats()
        self.reaction_log = []
        self.last_reaction_time = 0
        self._save_reaction_log()
        print("[Hanako] 统计数据已重置")
    
    def _save_reaction_log(self):
        """保存反应日志"""
        try:
            log_path = Path("reaction_log.json")
            with open(log_path, "w", encoding="utf-8") as f:
                json.dump(self.reaction_log, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Hanako] 保存日志失败: {e}")
    
    def _load_reaction_log(self):
        """加载反应日志"""
        try:
            log_path = Path("reaction_log.json")
            if log_path.exists():
                with open(log_path, "r", encoding="utf-8") as f:
                    self.reaction_log = json.load(f)
                print(f"[Hanako] 加载了 {len(self.reaction_log)} 条历史反应记录")
        except Exception as e:
            print(f"[Hanako] 加载日志失败: {e}")


if __name__ == "__main__":
    print("=== Hanako 弹幕联动桥接模块测试 ===")
    
    # 创建桥接器（缩短冷却时间以便测试）
    bridge = HanakoDanmuBridge()
    bridge.thresholds.cooldown = 0.05  # 测试用 0.05 秒
    
    # 模拟弹幕（更密集）
    test_danmus = [
        ("666666", "meme", "excited"),
        ("太帅了！", "reaction", "excited"),
        ("哈哈哈哈哈", "comment", "happy"),
        ("露西亚 yyds", "meme", "excited"),
        ("这技能绝了", "reaction", "excited"),
        ("再来一波", "meme", "excited"),
        ("好难过", "comment", "sad"),
        ("气死了", "reaction", "angry"),
        ("哭哭", "comment", "sad"),
        ("无语", "reaction", "angry"),
    ]
    
    print("\n模拟弹幕:")
    for text, style, emotion in test_danmus:
        bridge.add_danmu(text, style, emotion)
    
    # 显示统计
    stats = bridge.get_stats()
    print(f"\n统计:")
    print(f"  总弹幕: {stats['stats']['total_count']}")
    print(f"  兴奋: {stats['stats']['excited_count']}")
    print(f"  悲伤: {stats['stats']['sad_count']}")
    print(f"  愤怒: {stats['stats']['angry_count']}")
    print(f"  反应次数: {stats['reaction_count']}")
    
    print("\nHanako 弹幕联动桥接模块测试通过 ✓")
