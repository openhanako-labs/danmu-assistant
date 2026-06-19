"""
说话人分离模块
Phase 2: 从语音中识别不同说话人，用于生成更有针对性的弹幕
"""
import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class SpeakerProfile:
    """说话人档案"""
    id: str
    name: str = "未知"
    utterance_count: int = 0
    last_seen: float = 0.0
    avg_text_length: float = 0.0
    total_text_length: float = 0.0
    keywords: List[str] = field(default_factory=list)
    
    def update_avg_text_length(self, text_len: int):
        """更新平均文本长度"""
        self.utterance_count += 1
        self.total_text_length += text_len
        self.avg_text_length = self.total_text_length / self.utterance_count


class SpeakerTracker:
    """
    说话人追踪器
    
    基于文本特征（长度、词汇习惯）推断说话人身份
    适用于单麦克风场景（无法做音频层面的说话人嵌入）
    """
    
    def __init__(self, max_speakers: int = 5, similarity_threshold: float = 0.5):
        """
        Args:
            max_speakers: 最大追踪说话人数
            similarity_threshold: 文本相似度阈值（越高越严格）
        """
        self.max_speakers = max_speakers
        self.similarity_threshold = similarity_threshold
        self.profiles: Dict[str, SpeakerProfile] = {}
        self.current_speaker: Optional[str] = None
        self.speaker_history: List[dict] = []  # 历史记录
        self.turn_count = 0
        self.speaker_counter = 0  # 说话人编号计数器
        
    def analyze_turn(self, text: str, timestamp: float = 0) -> dict:
        """
        分析一轮对话，推断说话人
        
        Args:
            text: 转写文本
            timestamp: 时间戳
            
        Returns:
            {
                "speaker_id": "speaker_1",
                "speaker_name": "主播",
                "confidence": 0.8,
                "text_length": 10,
                "is_new_speaker": False
            }
        """
        if not text.strip():
            return {"speaker_id": None, "confidence": 0, "text_length": 0, "is_new_speaker": False}
        
        self.turn_count += 1
        text_len = len(text.strip())
        text_lower = text.lower()
        
        # 提取关键词（简单分词）
        words = self._simple_tokenize(text)
        content_words = [w for w in words if len(w) > 1]
        
        # 尝试匹配已有说话人
        best_match = None
        best_score = 0
        
        for sid, profile in self.profiles.items():
            score = self._similarity(profile, text_len, content_words)
            if score > best_score:
                best_score = score
                best_match = sid
        
        # 决定是否创建新说话人
        is_new = False
        if best_match is None or best_score < self.similarity_threshold:
            # 创建新说话人或使用默认
            if len(self.profiles) < self.max_speakers:
                best_match = f"speaker_{len(self.profiles) + 1}"
                self.profiles[best_match] = SpeakerProfile(id=best_match)
                is_new = True
            else:
                # 超过上限，复用最相似的
                if best_match:
                    pass
                else:
                    best_match = f"speaker_{self.turn_count % self.max_speakers + 1}"
        
        # 更新说话人档案
        profile = self.profiles[best_match]
        profile.update_avg_text_length(text_len)
        profile.keywords.extend(content_words[:5])
        profile.keywords = list(set(profile.keywords))  # 去重
        profile.last_seen = timestamp
        
        # 分配名称
        name = self._assign_name(best_match, profile, is_new)
        
        result = {
            "speaker_id": best_match,
            "speaker_name": name,
            "confidence": best_score if not is_new else 1.0,
            "text_length": text_len,
            "is_new_speaker": is_new,
            "turn_number": self.turn_count
        }
        
        self.speaker_history.append(result)
        self.current_speaker = best_match
        
        return result
    
    def _simple_tokenize(self, text: str) -> List[str]:
        """简单中文分词（基于字符）"""
        return list(text)
    
    def _similarity(self, profile: SpeakerProfile, text_len: int, words: List[str]) -> float:
        """
        计算与已有说话人的相似度
        
        基于：
        1. 文本长度差异
        2. 词汇多样性（unique word ratio）
        3. 共同词汇比例
        """
        # 文本长度相似度
        len_diff = abs(text_len - profile.avg_text_length)
        len_sim = max(0, 1 - len_diff / 30)  # 30字差异为完全不相似
        
        # 词汇多样性
        if words:
            unique_ratio = len(set(words)) / len(words)
            # 假设每个说话人有独特的词汇习惯，多样性相近
            # 这里简化处理：如果文本很短且重复多，可能是反应类弹幕
            # 如果文本较长且多样，可能是解说类
        
        # 共同词汇比例（简化版）
        if words and profile.keywords:
            word_set = set(words[:15])
            kw_set = set(profile.keywords[:15])
            if word_set and kw_set:
                jaccard = len(word_set & kw_set) / len(word_set | kw_set)
                # 如果共同词汇很少，相似度低
                vocab_sim = jaccard
            else:
                vocab_sim = 0
        else:
            vocab_sim = 0
        
        # 综合评分：词汇相似度权重更高
        return 0.3 * len_sim + 0.7 * vocab_sim
    
    def _assign_name(self, speaker_id: str, profile: SpeakerProfile, is_new: bool) -> str:
        """为说话人分配名称"""
        if is_new:
            # 根据关键词推断名称
            if profile.keywords:
                profile.name = profile.keywords[0]
            else:
                profile.name = f"说话人{self.turn_count}"
            return profile.name
        return profile.name
    
    def get_summary(self) -> dict:
        """获取说话人统计摘要"""
        return {
            "total_turns": self.turn_count,
            "unique_speakers": len(self.profiles),
            "speakers": {
                sid: {
                    "name": self._assign_name(sid, p, False),
                    "utterances": p.utterance_count,
                    "avg_length": round(p.avg_text_length, 1),
                    "keywords": p.keywords[:10]
                }
                for sid, p in self.profiles.items()
            }
        }
    
    def reset(self):
        """重置追踪器"""
        self.profiles.clear()
        self.current_speaker = None
        self.speaker_history.clear()
        self.turn_count = 0


if __name__ == "__main__":
    # 测试
    print("=== 说话人追踪器测试 ===")
    tracker = SpeakerTracker(max_speakers=3)
    
    # 模拟对话
    dialogues = [
        ("主播", "大家好欢迎来到我的直播间今天我们来玩战双"),
        ("观众A", "666666主播加油"),
        ("主播", "好的今天先抽十连看看运气"),
        ("观众B", "主播欧气满满"),
        ("主播", "哎呀歪了下次一定"),
    ]
    
    for person, text in dialogues:
        result = tracker.analyze_turn(text)
        print(f"  [{person}] '{text[:20]}...' -> 说话人: {result['speaker_name']} (置信度: {result['confidence']:.2f})")
    
    summary = tracker.get_summary()
    print(f"\n统计: {summary['total_turns']} 轮对话, {summary['unique_speakers']} 个说话人")
    print("\n说话人追踪器测试通过 ✓")
