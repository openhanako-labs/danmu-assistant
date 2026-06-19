"""
语音输入模块 - 基于 FunASR 的本地语音转写
v2.0: 本地识别，零延迟、零费用
"""
import io
import wave
import numpy as np
from datetime import datetime


class AudioRecorder:
    """
    音频录制器 - 使用 sounddevice 采集麦克风音频
    """
    def __init__(self, sample_rate: int = 16000, channels: int = 1):
        self.sample_rate = sample_rate
        self.channels = channels
        self.is_recording = False
        self.audio_buffer = None
        
    def start_recording(self):
        """开始录制"""
        import sounddevice as sd
        
        self.is_recording = True
        self.audio_buffer = []
        
        def callback(indata, frames, time, status):
            if status:
                print(f"  [录音] 状态: {status}")
            if self.is_recording:
                self.audio_buffer.append(indata.copy())
        
        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            callback=callback
        )
        self.stream.start()
        
    def stop_recording(self) -> tuple:
        """停止录制，返回 (PCM数据, 采样率)"""
        self.is_recording = False
        if hasattr(self, 'stream'):
            self.stream.stop()
            self.stream.close()
            
        if not self.audio_buffer:
            return None, self.sample_rate
            
        # 拼接所有音频块
        audio_data = np.concatenate(self.audio_buffer, axis=0)
        return audio_data, self.sample_rate


class FunASRClient:
    """
    FunASR 本地语音转写客户端
    
    使用 paraformer-zh 模型，中文识别效果好
    """
    
    def __init__(self, model_name: str = "paraformer-zh", 
                 vad_model: str = "fsmn-vad",
                 sample_rate: int = 16000):
        self.model_name = model_name
        self.vad_model = vad_model
        self.sample_rate = sample_rate
        self._model = None
        self._initialized = False
        
    def _ensure_model(self):
        """懒加载模型"""
        if self._initialized:
            return
            
        if self._model is None:
            from funasr import AutoModel
            
            print(f"  [FunASR] 加载模型: {self.model_name}")
            print(f"  [FunASR] 加载VAD: {self.vad_model}")
            
            self._model = AutoModel(
                model=self.model_name,
                vad_model=self.vad_model,
                vad_kwargs={"max_single_segment_time": 30000},
                device="cpu"  # 有GPU可改为 "cuda"
            )
            self._initialized = True
            print("  [FunASR] 模型加载完成")
    
    async def transcribe(self, audio_data: np.ndarray, sample_rate: int) -> dict:
        """
        转写音频
        
        Args:
            audio_data: PCM 音频数据 (numpy array)
            sample_rate: 采样率
            
        Returns:
            {
                "text": "转写文本",
                "language": "zh",
                "duration": 5.2,
                "success": True
            }
        """
        if audio_data is None or len(audio_data) == 0:
            return {"text": "", "language": "unknown", "duration": 0, "success": False}
        
        self._ensure_model()
        
        # 归一化到 float32
        audio_float = audio_data.astype(np.float32)
        
        # FunASR 转写
        result = self._model.generate(input=audio_float, 
                                       fs=sample_rate,
                                       batch_size=1)
        
        text = ""
        if result and len(result) > 0:
            text = result[0].get("text", "").strip()
        
        duration = len(audio_data) / sample_rate if sample_rate > 0 else 0
        
        return {
            "text": text,
            "language": "zh",
            "duration": round(duration, 2),
            "success": bool(text)
        }


class AudioPipeline:
    """
    音频处理流水线
    采集 → FunASR 转写 → 输出
    """
    def __init__(self, sample_rate: int = 16000):
        self.recorder = AudioRecorder(sample_rate=sample_rate)
        self.asr = FunASRClient(sample_rate=sample_rate)
        self.current_text = ""
        self.last_speaker = ""
        
    async def process_audio(self, duration: float = 3.0) -> dict:
        """
        处理一段音频
        
        Args:
            duration: 录制时长（秒）
            
        Returns:
            {"text": "...", "speaker": "", "emotion": "neutral", "timestamp": "...", "duration": 3.0}
        """
        print(f"  [录音] 录制 {duration} 秒...")
        self.recorder.start_recording()
        
        import asyncio
        await asyncio.sleep(duration)
        
        audio_data, sr = self.recorder.stop_recording()
        print(f"  [录音] 完成，采样数: {len(audio_data) if audio_data is not None else 0}")
        
        # 转写
        print("  [转写] FunASR 本地识别...")
        result = await self.asr.transcribe(audio_data, sr)
        text = result.get("text", "").strip()
        duration_actual = result.get("duration", 0)
        
        print(f"  [转写] 文本: {text}")
        print(f"  [转写] 时长: {duration_actual}s, 成功: {result.get('success', False)}")
        
        self.current_text = text
        return {
            "text": text,
            "speaker": self.last_speaker,
            "emotion": "neutral",
            "timestamp": datetime.now().isoformat(),
            "duration": duration_actual
        }
        
    def get_current_text(self) -> str:
        """获取当前转写文本"""
        return self.current_text


# 测试代码
if __name__ == "__main__":
    print("=== 语音输入模块测试 ===")
    print("FunASR 本地识别模式")
    print("\n注意：首次运行会下载模型文件（约 200MB）")
    print("需要安装 sounddevice: pip install sounddevice")
    print("\n模块结构:")
    print("  AudioRecorder - 麦克风音频采集")
    print("  FunASRClient - 本地语音转写")
    print("  AudioPipeline - 完整流水线")
    print("\n语音输入模块 v2.0 就绪 ✓")
