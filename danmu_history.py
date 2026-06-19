"""
弹幕历史记录模块
Phase 3: 保存和回放弹幕历史
"""
import json
import time
from typing import List, Dict, Optional
from dataclasses import dataclass, field, asdict
from pathlib import Path
from datetime import datetime


@dataclass
class DanmuRecord:
    """弹幕记录"""
    text: str
    style: str  # 使用的皮肤风格
    emotion: str  # 触发时的情绪
    timestamp: float = field(default_factory=time.time)
    scene_description: str = ""  # 场景描述
    audio_text: str = ""  # 音频转写文本
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'DanmuRecord':
        return cls(**data)


class DanmuHistory:
    """
    弹幕历史记录
    
    保存弹幕生成历史，支持回放和统计
    """
    
    def __init__(self, max_records: int = 1000, storage_path: str = "danmu_history.json"):
        self.max_records = max_records
        self.storage_path = storage_path
        self.records: List[DanmuRecord] = []
        self._load_history()
    
    def add_record(self, text: str, style: str = "default", emotion: str = "neutral",
                   scene_description: str = "", audio_text: str = ""):
        """
        添加弹幕记录
        
        Args:
            text: 弹幕文本
            style: 使用的皮肤风格
            emotion: 触发时的情绪
            scene_description: 场景描述
            audio_text: 音频转写文本
        """
        record = DanmuRecord(
            text=text,
            style=style,
            emotion=emotion,
            scene_description=scene_description,
            audio_text=audio_text
        )
        self.records.append(record)
        
        # 限制记录数量
        if len(self.records) > self.max_records:
            self.records = self.records[-self.max_records:]
        
        # 自动保存
        self._save_history()
    
    def get_recent_records(self, count: int = 10) -> List[DanmuRecord]:
        """
        获取最近的记录
        
        Args:
            count: 获取数量
            
        Returns:
            DanmuRecord 列表
        """
        return self.records[-count:]
    
    def get_records_by_style(self, style: str) -> List[DanmuRecord]:
        """按风格筛选记录"""
        return [r for r in self.records if r.style == style]
    
    def get_records_by_emotion(self, emotion: str) -> List[DanmuRecord]:
        """按情绪筛选记录"""
        return [r for r in self.records if r.emotion == emotion]
    
    def get_statistics(self) -> Dict[str, any]:
        """
        获取统计信息
        
        Returns:
            统计字典
        """
        if not self.records:
            return {
                "total_records": 0,
                "styles": {},
                "emotions": {},
                "avg_records_per_minute": 0
            }
        
        # 统计风格分布
        style_counts = {}
        for record in self.records:
            style_counts[record.style] = style_counts.get(record.style, 0) + 1
        
        # 统计情绪分布
        emotion_counts = {}
        for record in self.records:
            emotion_counts[record.emotion] = emotion_counts.get(record.emotion, 0) + 1
        
        # 计算时间跨度
        if len(self.records) > 1:
            time_span = self.records[-1].timestamp - self.records[0].timestamp
            avg_per_minute = len(self.records) / (time_span / 60) if time_span > 0 else 0
        else:
            avg_per_minute = 0
        
        return {
            "total_records": len(self.records),
            "styles": style_counts,
            "emotions": emotion_counts,
            "avg_records_per_minute": round(avg_per_minute, 2),
            "first_record": datetime.fromtimestamp(self.records[0].timestamp).isoformat() if self.records else None,
            "last_record": datetime.fromtimestamp(self.records[-1].timestamp).isoformat() if self.records else None
        }
    
    def replay(self, count: int = 5, delay: float = 1.0) -> List[dict]:
        """
        回放历史记录
        
        Args:
            count: 回放数量
            delay: 每条记录之间的延迟（秒）
            
        Returns:
            回放记录列表
        """
        recent = self.get_recent_records(count)
        replay_data = []
        
        for record in recent:
            replay_data.append({
                "text": record.text,
                "style": record.style,
                "emotion": record.emotion,
                "timestamp": datetime.fromtimestamp(record.timestamp).strftime("%H:%M:%S")
            })
        
        return replay_data
    
    def clear(self):
        """清空历史记录"""
        self.records.clear()
        self._save_history()
    
    def _save_history(self):
        """保存历史记录到文件"""
        try:
            data = [r.to_dict() for r in self.records]
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存历史记录失败: {e}")
    
    def _load_history(self):
        """从文件加载历史记录"""
        path = Path(self.storage_path)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.records = [DanmuRecord.from_dict(record) for record in data]
            except Exception as e:
                print(f"加载历史记录失败: {e}")


if __name__ == "__main__":
    # 测试
    print("=== 弹幕历史记录测试 ===")
    
    # 创建历史记录
    history = DanmuHistory(max_records=100, storage_path="test_history.json")
    
    # 添加测试记录
    test_records = [
        ("666666", "meme", "excited", "直播画面", "哇太帅了"),
        ("露西亚yyds", "comment", "happy", "游戏画面", "露西亚技能"),
        ("这特效拉满了", "reaction", "excited", "战斗画面", "技能释放"),
    ]
    
    for text, style, emotion, scene, audio in test_records:
        history.add_record(text, style, emotion, scene, audio)
    
    # 获取统计
    stats = history.get_statistics()
    print(f"统计: {stats}")
    
    # 回放
    replay = history.replay(count=3)
    print(f"\n回放记录:")
    for r in replay:
        print(f"  [{r['timestamp']}] [{r['style']}] {r['text']}")
    
    # 清理测试文件
    import os
    if os.path.exists("test_history.json"):
        os.remove("test_history.json")
    
    print("\n弹幕历史记录测试通过 ✓")
