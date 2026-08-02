"""
Scene 构建模块 - 将截屏和语音拼成一条完整"场景"
Phase 1: MVP 核心链路
"""
from dataclasses import dataclass, asdict
from typing import Optional
from datetime import datetime


@dataclass
class Scene:
    """
    场景数据类
    包含一次截屏 + 对应的语音转写结果
    """
    timestamp: float
    screenshot_base64: str  # Base64 编码的图片
    audio_text: str = ""    # 音频转写文本
    audio_speaker: str = "" # 说话人
    audio_emotion: str = "neutral"  # 情绪标签
    scene_type: str = "unknown"  # 场景类型（直播/代码/聊天/游戏/桌面）
    
    def to_api_message(self) -> dict:
        """
        转换为 LLM API 可用的消息格式
        
        Returns:
            包含图片和文本的消息字典
        """
        return {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": self._build_text_context()
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{self.screenshot_base64}"
                    }
                }
            ]
        }
    
    def _build_text_context(self) -> str:
        """
        构建文本上下文
        
        Returns:
            格式化的文本上下文
        """
        parts = []
        if self.audio_text:
            parts.append(f"音频: {self.audio_text}")
        if self.audio_speaker:
            parts.append(f"说话人: {self.audio_speaker}")
        if self.audio_emotion and self.audio_emotion != "neutral":
            parts.append(f"情绪: {self.audio_emotion}")
        if self.scene_type and self.scene_type != "unknown":
            parts.append(f"场景: {self.scene_type}")
            
        return " | ".join(parts) if parts else "（无音频信息）"
    
    def to_danmu_prompt_context(self) -> dict:
        """
        转换为弹幕生成的上下文数据
        
        Returns:
            包含场景信息的字典
        """
        return {
            "image_description": "（由视觉模型生成）",  # 实际会使用 image_base64
            "audio_text": self.audio_text,
            "speaker": self.audio_speaker,
            "emotion": self.audio_emotion,
            "scene_type": self.scene_type,
            "timestamp": self.timestamp
        }
    
    def to_json(self) -> str:
        """序列化为 JSON 字符串"""
        import json
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> "Scene":
        """从 JSON 字符串反序列化"""
        import json
        data = json.loads(json_str)
        return cls(**data)
    
    def __str__(self) -> str:
        """字符串表示"""
        return (
            f"Scene({self.timestamp:.2f} | "
            f"音频: {self.audio_text[:20] if self.audio_text else '无'} | "
            f"类型: {self.scene_type})"
        )


# 测试代码
if __name__ == "__main__":
    print("=== Scene 构建模块测试 ===")
    
    # 创建测试场景
    test_scene = Scene(
        timestamp=1687000000.0,
        screenshot_base64="test_base64_data",
        audio_text="哇这个技能特效太帅了！",
        audio_speaker="主播",
        audio_emotion="兴奋",
        scene_type="直播"
    )
    
    print(f"场景: {test_scene}")
    print(f"\nAPI 消息格式:")
    print(test_scene.to_api_message())
    print(f"\n弹幕上下文:")
    print(test_scene.to_danmu_prompt_context())
    print(f"\nJSON 序列化:")
    print(test_scene.to_json())
    
    # 测试反序列化
    print("\n反序列化测试:")
    restored = Scene.from_json(test_scene.to_json())
    print(f"恢复场景: {restored}")
    
    print("\nScene 构建模块测试通过 ✓")
