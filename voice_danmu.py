"""
语音理解弹幕 - 麦克风收音 + ASREngine + AI 理解生成弹幕
"""
import os
import sys
import time
import threading
import queue
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import sounddevice as sd

from asr_engine import ASREngine, ApiASREngine, FasterWhisperEngine, _resample

# 国内镜像
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")


class VoiceDanmu:
    """语音理解弹幕。"""

    def __init__(self, overlay, config: dict, on_danmu=None):
        self.overlay = overlay
        self.config = config
        self.on_danmu = on_danmu
        self.running = False
        self.paused = False
        self._thread = None
        self._audio_queue = queue.Queue(maxsize=20)

        # 初始化识别引擎（按优先级）
        self.engine: ASREngine | None = None
        self._init_engine()

    # ==================== 引擎初始化 ====================

    def _init_engine(self):
        voice_cfg = self.config.get("voice", {})
        asr_api = voice_cfg.get("asr_api", {})
        cpp_cfg = voice_cfg.get("whisper_cpp", {})

        # 第一优先：ASR API
        if asr_api.get("provider") and asr_api.get("base_url"):
            self.engine = ApiASREngine(asr_api)
            print(f'[voice] 识别引擎: ASR API ({asr_api.get("provider")})', flush=True)
            return

        # 第二优先：whisper.cpp
        if cpp_cfg.get("enabled"):
            exe = cpp_cfg.get("exe_path", "")
            model = cpp_cfg.get("model_path", "")
            if exe and model and os.path.isfile(exe) and os.path.isfile(model):
                self.engine = CppASREngine(
                    exe, model,
                    language=cpp_cfg.get("language", "zh"),
                    threads=cpp_cfg.get("threads", 4),
                )
                print('[voice] 识别引擎: whisper.cpp', flush=True)
                return
            print('[voice] whisper.cpp 路径无效，降级到 faster-whisper', flush=True)

        # 第三优先：faster-whisper
        model_size = voice_cfg.get("whisper_model", "base")
        device = voice_cfg.get("device", "cpu")
        compute_type = voice_cfg.get("compute_type", "int8")
        self.engine = FasterWhisperEngine(model_size, device, compute_type)
        print(f'[voice] 识别引擎: faster-whisper ({model_size})', flush=True)

    # ==================== 主循环 ====================

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print('[voice] 语音理解弹幕已启动', flush=True)

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=2)

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def _loop(self):
        voice_cfg = self.config.get("voice", {})
        configured_sr = voice_cfg.get("sample_rate", 48000)
        channels = voice_cfg.get("channels", 1)
        silence_threshold = voice_cfg.get("silence_threshold", 0.005)
        silence_duration = voice_cfg.get("silence_duration", 1.2)  # 静音1.2秒算一句话结束
        max_buffer_duration = voice_cfg.get("max_buffer_duration", 8.0)  # 最多攒8秒

        device_id, sample_rate = self._pick_input_device(configured_sr)
        print(f'[voice] 录音设备: {sd.query_devices(device_id, "input")["name"]} ({sample_rate}Hz)', flush=True)

        def audio_callback(indata, frames, time_info, status):
            if not self.paused:
                try:
                    self._audio_queue.put_nowait(indata.copy())
                except queue.Full:
                    pass

        with sd.InputStream(samplerate=sample_rate, channels=channels,
                           dtype='float32', blocksize=1024,
                           device=device_id, callback=audio_callback):
            speech_buffer: list[np.ndarray] = []
            silence_counter = 0.0
            is_speaking = False
            max_samples = int(sample_rate * max_buffer_duration)

            while self.running:
                try:
                    data = self._audio_queue.get(timeout=0.1)
                    speech_buffer.append(data)

                    # 计算当前块 RMS
                    audio_1d = data.flatten()
                    rms = float(np.sqrt(np.mean(audio_1d ** 2)))

                    if rms > silence_threshold:
                        silence_counter = 0.0
                        if not is_speaking:
                            is_speaking = True
                    else:
                        silence_counter += len(audio_1d) / sample_rate

                    # 检测到静音 + 有话 → 提交识别
                    if is_speaking and silence_counter >= silence_duration:
                        total_samples = sum(len(b) for b in speech_buffer)
                        if total_samples > 0:
                            audio = np.concatenate(speech_buffer)[:max_samples]
                            text = self.engine.recognize(audio, sample_rate) if self.engine else ""
                            if text:
                                print(f'[voice] 识别到: "{text}"', flush=True)
                                if self.on_danmu:
                                    self.on_danmu(text)
                            else:
                                print(f'[voice] 识别为空 (缓冲{total_samples/sample_rate:.1f}秒)', flush=True)
                        speech_buffer.clear()
                        is_speaking = False
                        silence_counter = 0.0

                    # 防止缓冲区无限增长
                    total_samples = sum(len(b) for b in speech_buffer)
                    if total_samples > max_samples:
                        audio = np.concatenate(speech_buffer)[:max_samples]
                        text = self.engine.recognize(audio, sample_rate) if self.engine else ""
                        if text:
                            print(f'[voice] 识别到(超长截断): "{text}"', flush=True)
                            if self.on_danmu:
                                self.on_danmu(text)
                        speech_buffer.clear()
                        is_speaking = False
                        silence_counter = 0.0

                except queue.Empty:
                    # 超时没数据，重置状态
                    if is_speaking and silence_counter >= silence_duration:
                        total_samples = sum(len(b) for b in speech_buffer)
                        if total_samples > 0:
                            audio = np.concatenate(speech_buffer)[:max_samples]
                            text = self.engine.recognize(audio, sample_rate) if self.engine else ""
                            if text:
                                print(f'[voice] 识别到: "{text}"', flush=True)
                                if self.on_danmu:
                                    self.on_danmu(text)
                        speech_buffer.clear()
                        is_speaking = False
                        silence_counter = 0.0
                    continue
                except Exception as e:
                    print(f'[voice] 错误: {e}', flush=True)

    # ==================== 设备选择 ====================

    def _pick_input_device(self, preferred_sr: int):
        devices = sd.query_devices()
        hostapis = sd.query_hostapis()
        input_devices = []
        for i in range(len(devices)):
            try:
                dev = sd.query_devices(i, 'input')
                if dev['max_input_channels'] > 0:
                    hostapi_name = hostapis[dev['hostapi']]['name']
                    dev_info = dict(dev)
                    dev_info['hostapi_name'] = hostapi_name
                    input_devices.append((i, dev_info))
            except ValueError:
                continue
        if not input_devices:
            raise RuntimeError("没有找到可用的麦克风设备")

        wasapi = [(i, d) for i, d in input_devices if 'WASAPI' in d.get('hostapi_name', '')]
        if wasapi:
            dev_id, dev = wasapi[0]
            default_sr = int(dev.get('default_samplerate', 48000))
            try:
                with sd.InputStream(device=dev_id, samplerate=preferred_sr, channels=1, dtype='float32'):
                    pass
                return dev_id, preferred_sr
            except Exception:
                return dev_id, default_sr

        dev_id, dev = input_devices[0]
        return dev_id, int(dev.get('default_samplerate', 16000))
