"""
实时流式引擎 - 截屏 + 语音 + Hanako 联动
v2.0: 真正的实时流式处理
"""
import asyncio
import time
import threading
import base64
from typing import Callable, Optional
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import PIL.Image

from screen_capture import capture_screen, compress_image
from audio_input import AudioPipeline
from inference import generate_danmu
from emotion_recognizer import EmotionRecognizer


@dataclass
class StreamEvent:
    """流式事件"""
    type: str  # "visual_change" / "audio_speech" / "combined"
    timestamp: float = field(default_factory=time.time)
    audio_text: str = ""
    speaker: str = ""
    emotion: str = "neutral"
    danmu_list: list = field(default_factory=list)


class StreamEngine:
    """
    实时流式引擎
    
    三条并行流水线：
    1. 截屏流水线：定时截屏 → 关键帧检测 → 画面分析 → 生成弹幕
    2. 语音流水线：麦克风采集 → Whisper 转写 → 情绪识别 → 生成弹幕
    3. Hanako 联动：接收 Hanako 事件 → 触发弹幕生成
    """
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.capture_config = self.config.get("capture", {})
        self.audio_config = self.config.get("audio", {})
        self.inference_config = self.config.get("inference", {})
        
        # 模块
        self.audio_pipeline = None  # 懒加载
        self.emotion_recognizer = EmotionRecognizer()
        
        # 状态
        self.is_running = False
        self._event_handlers: list = []
        self._screenshots_taken = 0
        self._audio_processed = 0
        self._danmu_generated = 0
        self._start_time = 0
        
        # 截屏上次时间
        self._last_screenshot_time = 0
        self._last_keyframe_text = ""
        
    def on_event(self, handler: Callable):
        """注册事件处理器"""
        self._event_handlers.append(handler)
    
    async def _trigger_event(self, event: StreamEvent):
        """触发事件处理器"""
        for handler in self._event_handlers:
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                handler(event)
    
    async def _process_visual(self):
        """
        视觉流水线：截屏 → 关键帧检测 → 生成弹幕
        
        使用简单的时间间隔 + 画面变化检测
        """
        interval = self.capture_config.get("interval", 5)
        quality = self.capture_config.get("quality", 70)
        min_interval = self.capture_config.get("min_interval", 3)  # 最短间隔（秒）
        
        while self.is_running:
            now = time.time()
            
            # 检查是否到了截屏时间
            if now - self._last_screenshot_time >= min_interval:
                try:
                    # 截屏
                    img = capture_screen(self.capture_config.get("screen_index", 0))
                    self._screenshots_taken += 1
                    
                    # 缩小图片再压缩，减少 API 传输量
                    w, h = img.size
                    max_w = 640
                    if w > max_w:
                        h = int(h * max_w / w)
                        w = max_w
                    img_small = img.resize((w, h), PIL.Image.LANCZOS)
                    compressed, b64 = compress_image(img_small, quality)
                    
                    print(f"  [截屏 #{self._screenshots_taken}] 大小={img.size}, 压缩后={len(compressed)}bytes", flush=True)
                    
                    # 简化画面描述（用颜色统计代替 CV 模型）
                    desc = self._describe_image_simple(img)
                    
                    # 如果画面变化不大，跳过
                    if desc == self._last_keyframe_text and now - self._last_screenshot_time < interval:
                        print(f"  [截屏] 画面无变化，跳过")
                        self._last_screenshot_time = now
                        continue
                    
                    print(f"  [截屏] 画面有变化，调用 LLM...")
                    self._last_keyframe_text = desc
                    
                    # 生成弹幕（视觉模式）
                    api_config = self.config.get("api", {})
                    danmu_list = await generate_danmu(
                        image_base64=b64,
                        audio_text="",
                        use_vision=True,
                        config=self.config
                    )
                    
                    if danmu_list:
                        event = StreamEvent(
                            type="visual_change",
                            audio_text="",
                            danmu_list=danmu_list
                        )
                        await self._trigger_event(event)
                        self._danmu_generated += len(danmu_list)
                        
                except Exception as e:
                    import traceback
                    print(f"  [截屏] 错误: {e}")
                    traceback.print_exc()
            
            self._last_screenshot_time = now
            await asyncio.sleep(1)  # 每秒检查一次
    
    def _describe_image_simple(self, img) -> str:
        """
        简单的画面描述（用颜色统计代替 CV 模型）
        返回 (描述字符串, 像素哈希) 用于变化检测
        """
        try:
            # 缩小到 50x50 做快速比较
            small = img.resize((50, 50))
            pixels = list(small.getdata())
            
            # RGB 均值
            avg_r = sum(p[0] for p in pixels) / len(pixels)
            avg_g = sum(p[1] for p in pixels) / len(pixels)
            avg_b = sum(p[2] for p in pixels) / len(pixels)
            
            # 像素哈希（用于快速比较）
            # 每个像素量化为 0-7，生成 8 位哈希
            hash_val = 0
            for p in pixels[::10]:  # 每 10 个像素取一个
                r, g, b = p
                val = (r >> 5) + ((g >> 5) << 3) + ((b >> 5) << 6)  # 0-511
                hash_val ^= (val * 2654435761)  # Knuth 哈希
            
            return f"rgb({avg_r:.0f},{avg_g:.0f},{avg_b:.0f}):{hash_val:x}"
        except:
            return "unknown:0"
    
    async def _process_audio(self):
        """
        语音流水线：麦克风采集 → Whisper 转写 → 生成弹幕
        """
        if not self.audio_config.get("enabled", True):
            return
        
        api_config = self.config.get("api", {})
        audio_interval = self.audio_config.get("interval", 10)  # 语音采集间隔（秒）
        vad_threshold = self.audio_config.get("vad_threshold", 0.02)  # 语音活动检测阈值
        
        # 初始化音频流水线（懒加载）
        if self.audio_pipeline is None:
            try:
                self.audio_pipeline = AudioPipeline()
                print("  [语音] FunASR 麦克风已就绪")
            except Exception as e:
                print(f"  [语音] 初始化失败: {e}")
                print("  [语音] 请安装 sounddevice: pip install sounddevice")
                return
        
        last_audio_time = 0
        
        while self.is_running:
            now = time.time()
            
            if now - last_audio_time >= audio_interval:
                try:
                    # 采集音频片段
                    result = await self.audio_pipeline.process_audio(duration=3.0)
                    text = result.get("text", "").strip()
                    
                    if not text:
                        last_audio_time = now
                        continue
                    
                    self._audio_processed += 1
                    
                    # 情绪识别
                    emotion_result = self.emotion_recognizer.recognize(text)
                    emotion_name = self.emotion_recognizer.get_emotion_name(emotion_result.emotion)
                    
                    # 生成弹幕（文本模式）
                    danmu_list = await generate_danmu(
                        audio_text=text,
                        speaker=result.get("speaker", ""),
                        use_vision=False,
                        config=self.config
                    )
                    
                    if danmu_list:
                        event = StreamEvent(
                            type="audio_speech",
                            audio_text=text,
                            speaker=result.get("speaker", ""),
                            emotion=emotion_name,
                            danmu_list=danmu_list
                        )
                        await self._trigger_event(event)
                        self._danmu_generated += len(danmu_list)
                        
                except Exception as e:
                    print(f"  [语音] 错误: {e}")
            
            last_audio_time = now
            await asyncio.sleep(1)
    
    async def start(self):
        """启动所有流水线"""
        self.is_running = True
        self._start_time = time.time()
        
        tasks = []
        
        # 截屏流水线
        if self.capture_config.get("enabled", True):
            tasks.append(asyncio.create_task(self._process_visual()))
            print("  [截屏] 流水线已启动")
        
        # 语音流水线
        if self.audio_config.get("enabled", True):
            tasks.append(asyncio.create_task(self._process_audio()))
        
        if not tasks:
            print("  [引擎] 所有输入已禁用，等待事件...")
        
        # 等待所有任务
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def stop(self):
        """停止所有流水线"""
        self.is_running = False
        elapsed = time.time() - self._start_time
        
        print(f"\n{'='*50}")
        print(f"  流式引擎已停止")
        print(f"  运行时间: {elapsed:.1f} 秒")
        print(f"  截屏次数: {self._screenshots_taken}")
        print(f"  语音处理: {self._audio_processed} 次")
        print(f"  弹幕生成: {self._danmu_generated} 条")
        print(f"{'='*50}")
    
    def get_stats(self) -> dict:
        """获取统计数据"""
        elapsed = time.time() - self._start_time if self._start_time else 0
        return {
            "screenshots": self._screenshots_taken,
            "audio_processed": self._audio_processed,
            "danmu_generated": self._danmu_generated,
            "running_time": round(elapsed, 1),
            "events_per_second": round((self._screenshots_taken + self._audio_processed) / elapsed, 2) if elapsed > 0 else 0
        }
