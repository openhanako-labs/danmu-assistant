"""
情绪识别模块
Phase 3: 从语音文本中识别情绪，用于生成更有针对性的弹幕
"""
from typing import Dict, List, Optional
from dataclasses import dataclass
import re


@dataclass
class EmotionResult:
    """情绪识别结果"""
    emotion: str  # 主要情绪
    confidence: float  # 置信度 (0-1)
    all_scores: Dict[str, float]  # 所有情绪分数
    
    def __post_init__(self):
        # 归一化分数
        total = sum(self.all_scores.values())
        if total > 0:
            self.all_scores = {k: v/total for k, v in self.all_scores.items()}
            self.confidence = max(self.all_scores.values())


class EmotionRecognizer:
    """
    情绪识别器
    
    基于关键词匹配和简单规则识别情绪
    适用于中文语音转写文本
    """
    
    # 情绪词典
    EMOTION_DICT = {
        "excited": {  # 兴奋
            "keywords": ["哇", "太帅了", "牛逼", "厉害了", "卧槽", "绝了", "666", "太强了"],
            "weight": 1.0
        },
        "happy": {  # 开心
            "keywords": ["哈哈", "开心", "好玩", "有趣", "笑死", "笑死我了", "哈哈哈"],
            "weight": 0.8
        },
        "surprised": {  # 惊讶
            "keywords": ["什么", "居然", "竟然", "没想到", "震惊", "卧槽", "啊这"],
            "weight": 0.9
        },
        "sad": {  # 悲伤
            "keywords": ["难过", "伤心", "哭了", "泪目", "好惨", "心疼", "呜呜"],
            "weight": 0.7
        },
        "angry": {  # 愤怒
            "keywords": ["气死", "怒", "无语", "离谱", "差评", "垃圾", "坑"],
            "weight": 0.8
        },
        "anticipation": {  # 期待
            "keywords": ["期待", "快点", "快更新", "什么时候", "等不及", "催更"],
            "weight": 0.7
        },
        "neutral": {  # 中性
            "keywords": ["好的", "可以", "嗯", "哦", "知道了", "下一关"],
            "weight": 0.5
        }
    }
    
    def __init__(self):
        self.keyword_scores = {}  # 关键词 -> 情绪分数
        self._build_keyword_dict()
    
    def _build_keyword_dict(self):
        """构建关键词词典"""
        for emotion, data in self.EMOTION_DICT.items():
            for keyword in data["keywords"]:
                if keyword not in self.keyword_scores:
                    self.keyword_scores[keyword] = 0
                self.keyword_scores[keyword] += data["weight"]
    
    def recognize(self, text: str) -> EmotionResult:
        """
        识别文本情绪
        
        Args:
            text: 语音转写文本
            
        Returns:
            EmotionResult 对象
        """
        if not text.strip():
            return EmotionResult(
                emotion="neutral",
                confidence=1.0,
                all_scores={e: 0 for e in self.EMOTION_DICT.keys()}
            )
        
        text_lower = text.lower()
        scores = {}
        
        # 基于关键词匹配
        for keyword, weight in self.keyword_scores.items():
            if keyword in text_lower:
                # 找到对应的情绪
                for emotion, data in self.EMOTION_DICT.items():
                    if keyword in data["keywords"]:
                        scores[emotion] = scores.get(emotion, 0) + weight
                        break
        
        # 检查标点符号（感叹号多可能表示兴奋）
        exclamation_count = text.count("!") + text.count("！")
        if exclamation_count > 2:
            scores["excited"] = scores.get("excited", 0) + 0.3
        
        # 检查重复字符（"666666" 表示兴奋）
        if re.search(r'(.)\1{3,}', text):
            scores["excited"] = scores.get("excited", 0) + 0.2
        
        # 确保所有情绪都有分数
        for emotion in self.EMOTION_DICT.keys():
            if emotion not in scores:
                scores[emotion] = 0
        
        # 找到主要情绪
        main_emotion = max(scores, key=scores.get)
        
        return EmotionResult(
            emotion=main_emotion,
            confidence=scores[main_emotion],
            all_scores=scores
        )
    
    def get_emotion_name(self, emotion: str) -> str:
        """获取情绪的中文名称"""
        names = {
            "excited": "兴奋",
            "happy": "开心",
            "surprised": "惊讶",
            "sad": "悲伤",
            "angry": "愤怒",
            "anticipation": "期待",
            "neutral": "中性"
        }
        return names.get(emotion, "未知")


if __name__ == "__main__":
    # 测试
    print("=== 情绪识别器测试 ===")
    recognizer = EmotionRecognizer()
    
    test_texts = [
        "哇这个技能太帅了！",
        "哈哈哈哈哈笑死我了",
        "什么？居然赢了？",
        "好难过，又输了",
        "气死我了，这游戏太坑了",
        "期待下一个角色",
        "好的，下一关",
    ]
    
    for text in test_texts:
        result = recognizer.recognize(text)
        emotion_name = recognizer.get_emotion_name(result.emotion)
        print(f"  [{emotion_name}] '{text}' -> 置信度: {result.confidence:.2f}")
    
    print("\n情绪识别器测试通过 ✓")
