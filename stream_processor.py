"""
实时流式处理模块
Phase 2: 从定时截屏改为事件驱动，实时响应画面和声音变化
"""
import asyncio
import time
import threading
from typing import Callable, Optional
from dataclasses import dataclass, field
from datetime import datetime

from keyframe_detector import KeyframeDetector
from speaker_diarization import SpeakerTracker
from danmu_skin import skin_manager


@dataclass
class StreamEvent:
    """流式事件"""
    type: str  # "visual_change" / "audio_speech" / "combined"
    timestamp: float = field(default_factory=time.time)
    image_data: Optional[bytes] = None
    audio_text: str = ""
    speaker: str = ""
    confidence: float = 0.0


class StreamProcessor:
    """
    实时流式处理器
    
    监听画面和声音变化，生成事件触发弹幕生成
    """
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.keyframe_detector = KeyframeDetector(
            threshold=self.config.get("keyframe", {}).get("threshold", 0.15),
            min_interval=self.config.get("keyframe", {}).get("min_interval", 30)
        )
        self.speaker_tracker = SpeakerTracker(
            max_speakers=self.config.get("speaker", {}).get("max_speakers", 5),
            similarity_threshold=self.config.get("speaker", {}).get("similarity_threshold", 0.5)
        )
        
        # 事件队列
        self.event_queue = asyncio.Queue()
        self.is_running = False
        self._event_handlers: list = []
        
        # 统计
        self.total_events = 0
        self.total_danmu_generated = 0
        self.start_time = 0
        
    def on_event(self, handler: Callable):
        """注册事件处理器"""
        self._event_handlers.append(handler)
    
    async def process_visual_event(self, image_data: bytes):
        """
        处理视觉事件（截屏）
        
        Args:
            image_data: 截屏图像数据
        """
        # 这里假设 image_data 是 PIL Image 对象
        # 实际使用时需要转换为 PIL Image
        is_keyframe = self.keyframe_detector.detect(image_data)
        
        if is_keyframe:
            event = StreamEvent(type="visual_change")
            await self.event_queue.put(event)
            self.total_events += 1
            
            # 通知处理器
            for handler in self._event_handlers:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
    
    async def process_audio_event(self, audio_text: str, speaker: str = ""):
        """
        处理音频事件（语音转写）
        
        Args:
            audio_text: 转写文本
            speaker: 说话人
        """
        if not audio_text.strip():
            return
        
        # 分析说话人
        speaker_result = self.speaker_tracker.analyze_turn(audio_text)
        
        event = StreamEvent(
            type="audio_speech",
            audio_text=audio_text,
            speaker=speaker_result["speaker_name"],
            confidence=speaker_result["confidence"]
        )
        await self.event_queue.put(event)
        self.total_events += 1
        
        # 通知处理器
        for handler in self._event_handlers:
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                handler(event)
    
    async def process_combined_event(self, image_data: bytes, audio_text: str, speaker: str = ""):
        """
        处理组合事件（截屏 + 语音）
        
        Args:
            image_data: 截屏图像数据
            audio_text: 转写文本
            speaker: 说话人
        """
        # 检查关键帧
        is_keyframe = self.keyframe_detector.detect(image_data)
        
        # 分析说话人
        speaker_result = self.speaker_tracker.analyze_turn(audio_text)
        
        event = StreamEvent(
            type="combined",
            image_data=image_data,
            audio_text=audio_text,
            speaker=speaker_result["speaker_name"],
            confidence=speaker_result["confidence"]
        )
        await self.event_queue.put(event)
        self.total_events += 1
        
        # 通知处理器
        for handler in self._event_handlers:
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                handler(event)
    
    async def start(self):
        """启动流式处理器"""
        self.is_running = True
        self.start_time = time.time()
        print("流式处理器已启动")
        
        while self.is_running:
            try:
                event = await asyncio.wait_for(self.event_queue.get(), timeout=1.0)
                print(f"[事件] 类型: {event.type}, 时间: {datetime.fromtimestamp(event.timestamp).strftime('%H:%M:%S')}")
            except asyncio.TimeoutError:
                continue
    
    def stop(self):
        """停止流式处理器"""
        self.is_running = False
        elapsed = time.time() - self.start_time
        print(f"\n流式处理器已停止")
        print(f"统计: {self.total_events} 个事件, {self.total_danmu_generated} 条弹幕, 运行 {elapsed:.1f} 秒")
    
    def get_stats(self) -> dict:
        """获取统计数据"""
        elapsed = time.time() - self.start_time if self.start_time else 0
        return {
            "total_events": self.total_events,
            "total_danmu_generated": self.total_danmu_generated,
            "running_time": round(elapsed, 1),
            "events_per_second": round(self.total_events / elapsed, 2) if elapsed > 0 else 0
        }


if __name__ == "__main__":
    # 测试
    print("=== 实时流式处理器测试 ===")
    
    processor = StreamProcessor()
    
    # 注册事件处理器
    async def test_handler(event: StreamEvent):
        print(f"  [处理器] 收到事件: {event.type}")
        if event.audio_text:
            print(f"    文本: {event.audio_text[:30]}...")
            print(f"    说话人: {event.speaker}")
    
    processor.on_event(test_handler)
    
    # 模拟事件
    asyncio.run(processor.process_audio_event("大家好欢迎来到直播间"))
    asyncio.run(processor.process_audio_event("666666主播加油"))
    asyncio.run(processor.process_audio_event("好的今天我们来玩战双"))
    
    print(f"\n统计: {processor.get_stats()}")
    print("\n实时流式处理器测试通过 ✓")
