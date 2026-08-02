"""
个性化风格模块
Phase 3: 根据用户喜好定制弹幕风格
"""
import json
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class UserPreference:
    """用户偏好设置"""
    # 弹幕风格偏好
    preferred_styles: List[str] = field(default_factory=lambda: ["meme", "comment", "reaction"])
    style_weights: Dict[str, float] = field(default_factory=lambda: {"meme": 0.3, "comment": 0.4, "reaction": 0.3})
    
    # 弹幕行为偏好
    max_danmu_count: int = 5
    max_danmu_length: int = 20
    include_emoji: bool = True
    include_references: bool = True  # 引用游戏/动漫梗
    
    # 情绪偏好
    prefer_emotions: List[str] = field(default_factory=lambda: ["excited", "happy"])
    
    # 自定义规则
    custom_rules: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'UserPreference':
        return cls(**data)


class StyleAdvisor:
    """
    风格建议器
    
    根据用户偏好生成弹幕风格建议
    """
    
    def __init__(self, preference: UserPreference = None):
        self.preference = preference or UserPreference()
        self.style_history: List[dict] = []  # 风格使用历史
    
    def get_style_distribution(self) -> Dict[str, float]:
        """
        获取风格分布
        
        Returns:
            风格名称 -> 权重 的字典
        """
        # 结合用户偏好和历史记录
        distribution = self.preference.style_weights.copy()
        
        # 根据历史记录调整
        if self.style_history:
            recent_styles = self.style_history[-10:]  # 最近 10 条
            style_counts = {}
            for record in recent_styles:
                style = record.get("style", "default")
                style_counts[style] = style_counts.get(style, 0) + 1
            
            # 如果某种风格使用过多，降低权重
            total = sum(style_counts.values())
            for style, count in style_counts.items():
                if count / total > 0.5:  # 超过 50%
                    distribution[style] = distribution.get(style, 0.3) * 0.7
        
        # 归一化
        total = sum(distribution.values())
        if total > 0:
            distribution = {k: v/total for k, v in distribution.items()}
        
        return distribution
    
    def suggest_danmu_style(self, emotion: str = "neutral") -> str:
        """
        根据情绪推荐弹幕风格
        
        Args:
            emotion: 情绪类型
            
        Returns:
            推荐风格
        """
        emotion_style_map = {
            "excited": "meme",
            "happy": "reaction",
            "surprised": "meme",
            "sad": "comment",
            "angry": "reaction",
            "anticipation": "meme",
            "neutral": "comment"
        }
        
        preferred = emotion_style_map.get(emotion, "comment")
        
        # 检查用户是否偏好这种风格
        if preferred in self.preference.preferred_styles:
            return preferred
        
        # 否则返回用户偏好的第一种风格
        return self.preference.preferred_styles[0] if self.preference.preferred_styles else "comment"
    
    def record_style_usage(self, style: str, danmu_text: str):
        """记录风格使用情况"""
        self.style_history.append({
            "style": style,
            "text": danmu_text[:50],
            "timestamp": len(self.style_history)
        })
        
        # 限制历史记录大小
        if len(self.style_history) > 100:
            self.style_history = self.style_history[-100:]
    
    def get_summary(self) -> dict:
        """获取风格建议摘要"""
        distribution = self.get_style_distribution()
        return {
            "style_distribution": distribution,
            "preferred_styles": self.preference.preferred_styles,
            "history_size": len(self.style_history)
        }


def load_preference(config_path: str = "user_preference.json") -> UserPreference:
    """
    加载用户偏好配置
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        UserPreference 对象
    """
    path = Path(config_path)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return UserPreference.from_dict(data)
    
    # 返回默认偏好
    return UserPreference()


def save_preference(preference: UserPreference, config_path: str = "user_preference.json"):
    """
    保存用户偏好配置
    
    Args:
        preference: UserPreference 对象
        config_path: 配置文件路径
    """
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(preference.to_dict(), f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    # 测试
    print("=== 个性化风格测试 ===")
    
    # 创建用户偏好
    preference = UserPreference(
        preferred_styles=["meme", "reaction"],
        style_weights={"meme": 0.4, "reaction": 0.4, "comment": 0.2}
    )
    
    advisor = StyleAdvisor(preference)
    
    # 测试风格分布
    distribution = advisor.get_style_distribution()
    print(f"风格分布: {distribution}")
    
    # 测试风格建议
    for emotion in ["excited", "happy", "neutral"]:
        style = advisor.suggest_danmu_style(emotion)
        print(f"情绪 [{emotion}] -> 推荐风格: {style}")
    
    # 记录使用历史
    advisor.record_style_usage("meme", "666666")
    advisor.record_style_usage("reaction", "太帅了！")
    
    # 获取摘要
    summary = advisor.get_summary()
    print(f"\n摘要: {summary}")
    
    print("\n个性化风格测试通过 ✓")
