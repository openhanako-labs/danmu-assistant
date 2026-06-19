"""
语音理解弹幕 - 麦克风收音 + ASR（API / whisper.cpp / faster-whisper）+ AI 理解生成弹幕
三层识别优先级：ASR API > whisper.cpp > faster-whisper
"""
import os
import sys
import time
import threading
import queue
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

# 国内镜像，解决 SSL 证书问题
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
        self._audio_queue = queue.Queue(maxsize=20)  # 最多积压20帧，防止内存爆炸

        # 三层识别引擎
        self.whisper = None        # faster-whisper (Python, fallback)
        self.cpp_engine = None     # whisper.cpp (本地 C++, 第二优先)

        self._init_engines()

    # ==================== 引擎初始化 ====================

    def _init_engines(self):
        """按优先级初始化：ASR API > whisper.cpp > faster-whisper。"""
        voice_cfg = self.config.get("voice", {})
        asr_api = voice_cfg.get("asr_api", {})
        cpp_cfg = voice_cfg.get("whisper_cpp", {})

        # 第一优先：ASR API
        if asr_api.get("provider") and asr_api.get("base_url"):
            print(f'[voice] 识别引擎: ASR API ({asr_api.get("provider")})', flush=True)
            return

        # 第二优先：whisper.cpp
        if cpp_cfg.get("enabled"):
            exe = cpp_cfg.get("exe_path", "")
            model = cpp_cfg.get("model_path", "")
            if exe and model and os.path.isfile(exe) and os.path.isfile(model):
                self.cpp_engine = {
                    "exe": exe,
                    "model": model,
                    "language": cpp_cfg.get("language", "zh"),
                    "threads": cpp_cfg.get("threads", 4),
                }
                print('[voice] 识别引擎: whisper.cpp (本地 C++)', flush=True)
                return
            else:
                print('[voice] whisper.cpp 路径无效，降级到 faster-whisper', flush=True)

        # 第三优先：faster-whisper
        self._init_faster_whisper()

    def _init_faster_whisper(self):
        """初始化 faster-whisper 模型。"""
        try:
            voice_cfg = self.config.get("voice", {})
            model_size = voice_cfg.get("whisper_model", "tiny")
            device = voice_cfg.get("device", "cpu")
            compute_type = voice_cfg.get("compute_type", "int8")
            print(f'[voice] 加载 Whisper 模型: {model_size} ({device}/{compute_type})...', flush=True)
            self.whisper = WhisperModel(model_size, device=device, compute_type=compute_type)
            print('[voice] Whisper 模型加载完成', flush=True)
        except Exception as e:
            print(f'[voice] Whisper 模型加载失败: {e}', flush=True)
            self.whisper = None

    # ==================== 主循环 ====================

    def start(self):
        """启动录音线程。"""
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        engine_name = self._get_engine_name()
        print(f'[voice] 语音理解弹幕已启动 [{engine_name}]', flush=True)

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=2)

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def _get_engine_name(self) -> str:
        voice_cfg = self.config.get("voice", {})
        asr_api = voice_cfg.get("asr_api", {})
        if asr_api.get("provider") and asr_api.get("base_url"):
            return f"ASR API ({asr_api.get('provider')})"
        if self.cpp_engine:
            return "whisper.cpp"
        if self.whisper:
            return "faster-whisper"
        return "无"

    def _pick_input_device(self, preferred_sr: int):
        """自动选择输入设备和采样率。优先 WASAPI，其次默认。"""
        # 找第一个有效的输入设备
        input_devices = [
            (i, sd.query_devices(i, 'input'))
            for i in range(sd.query_devices())
            if sd.query_devices(i, 'input')['max_input_channels'] > 0
        ]

        if not input_devices:
            raise RuntimeError("没有找到可用的麦克风设备")

        # 优先 WASAPI（低延迟）
        wasapi_devices = [(i, d) for i, d in input_devices if 'WASAPI' in d['hostapi']]
        if wasapi_devices:
            dev_id, dev = wasapi_devices[0]
            default_sr = int(dev.get('default_samplerate', 48000))
            # 如果配置的采样率不支持，用设备默认的
            if preferred_sr == default_sr:
                return dev_id, preferred_sr
            # 尝试配置的，不行就用默认的
            try:
                with sd.InputStream(device=dev_id, samplerate=preferred_sr, channels=1, dtype='float32'):
                    pass
                return dev_id, preferred_sr
            except Exception:
                return dev_id, default_sr

        # fallback：第一个输入设备
        dev_id, dev = input_devices[0]
        default_sr = int(dev.get('default_samplerate', 16000))
        return dev_id, default_sr

    def _loop(self):
        """后台循环：录音 → 识别 → 回调。"""
        voice_cfg = self.config.get("voice", {})
        configured_sr = voice_cfg.get("sample_rate", 48000)
        channels = voice_cfg.get("channels", 1)
        chunk_duration = voice_cfg.get("chunk_duration", 1.5)
        silence_threshold = voice_cfg.get("silence_threshold", 0.01)
        min_voice_ratio = voice_cfg.get("min_voice_ratio", 0.1)

        # 自动选择设备和采样率
        device_id, sample_rate = self._pick_input_device(configured_sr)
        chunk_samples = int(sample_rate * chunk_duration)
        print(f'[voice] 录音设备: {sd.query_devices(device_id, "input")["name"]} ({sample_rate}Hz)', flush=True)

        def audio_callback(indata, frames, time_info, status):
            if status:
                pass
            if not self.paused:
                self._audio_queue.put(indata.copy())

        with sd.InputStream(samplerate=sample_rate, channels=channels,
                           dtype='float32', blocksize=1024,
                           device=device_id,
                           callback=audio_callback):
            buffer = []
            while self.running:
                try:
                    data = self._audio_queue.get(timeout=1.0)
                    buffer.append(data)

                    total_samples = sum(len(b) for b in buffer)
                    if total_samples >= chunk_samples:
                        audio = np.concatenate(buffer)[:chunk_samples]
                        buffer = []

                        # 跳过静音检查，提高响应速度
                        audio_1d = audio.flatten()
                        text = self._recognize(audio_1d, sample_rate)
                        if text and self.on_danmu:
                            self.on_danmu(text)
                except queue.Empty:
                    continue
                except Exception as e:
                    print(f'[voice] 错误: {e}', flush=True)

    # ==================== 识别入口（三层优先级）====================

    def _recognize(self, audio, sample_rate) -> str:
        """
        识别优先级：
        1. ASR API（远程）
        2. whisper.cpp（本地 C++）
        3. faster-whisper（Python fallback）
        """
        # 第一优先：ASR API
        text = self._recognize_api(audio, sample_rate)
        if text is not None:
            return text

        # 第二优先：whisper.cpp
        text = self._recognize_cpp(audio, sample_rate)
        if text is not None:
            return text

        # 第三优先：faster-whisper
        return self._recognize_local(audio, sample_rate)

    # ==================== 第一层：ASR API ====================

    def _recognize_api(self, audio, sample_rate) -> str | None:
        """远程 ASR API。返回 None = 未配置或失败（走 fallback）。"""
        try:
            voice_cfg = self.config.get("voice", {})
            asr_api = voice_cfg.get("asr_api", {})
            if not asr_api:
                return None
            provider = asr_api.get("provider", "")
            base_url = asr_api.get("base_url", "")
            api_key = asr_api.get("api_key", "")
            model = asr_api.get("model", "whisper-1")

            if not provider or not base_url:
                return None

            wav_bytes = self._audio_to_wav(audio, sample_rate)

            if provider == "openai":
                url = f"{base_url}/audio/transcriptions"
                boundary = "----DanmuBoundary"
                body = (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n'
                    f"Content-Type: audio/wav\r\n\r\n"
                ).encode() + wav_bytes + f"\r\n--{boundary}--\r\n".encode()
                headers = {
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "Authorization": f"Bearer {api_key}",
                }
                req = urllib.request.Request(url, data=body, headers=headers, method="POST")

            elif provider == "siliconflow":
                url = f"{base_url}/audio/transcriptions"
                boundary = "----DanmuBoundary"
                body = (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n'
                    f"Content-Type: audio/wav\r\n\r\n"
                ).encode() + wav_bytes + (
                    f"\r\n--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="model"\r\n\r\n'
                    f"{model}\r\n--{boundary}--\r\n"
                ).encode()
                headers = {
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "Authorization": f"Bearer {api_key}",
                }
                req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            elif provider == "stepfun":
                url = f"{base_url}/audio/transcriptions"
                boundary = "----DanmuBoundary"
                body = (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n'
                    f"Content-Type: audio/wav\r\n\r\n"
                ).encode() + wav_bytes + (
                    f"\r\n--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="model"\r\n\r\n'
                    f"{model}\r\n--{boundary}--\r\n"
                ).encode()
                headers = {
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "Authorization": f"Bearer {api_key}",
                }
                req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            else:
                return None

            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))

            text = result.get("text", "").strip()
            return text if text else None

        except Exception as e:
            print(f'[voice] ASR API 失败 (fallback 本地): {e}', flush=True)
            return None

    # ==================== 第二层：whisper.cpp ====================

    def _recognize_cpp(self, audio, sample_rate) -> str | None:
        """whisper.cpp 本地识别。返回 None = 未配置或失败（走 fallback）。"""
        if not self.cpp_engine:
            return None

        try:
            # 把音频写成临时 wav 文件
            wav_path = self._audio_to_wav_file(audio, sample_rate)

            cmd = [
                self.cpp_engine["exe"],
                "--model", self.cpp_engine["model"],
                "--language", self.cpp_engine.get("language", "zh"),
                "--threads", str(self.cpp_engine.get("threads", 4)),
                "--file", wav_path,
                "--output-txt",
                "--output-file", wav_path.replace(".wav", ""),
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )

            # 清理临时文件
            try:
                os.remove(wav_path)
            except OSError:
                pass

            if result.returncode != 0:
                print(f'[voice] whisper.cpp 错误: {result.stderr[:200]}', flush=True)
                return None

            # 读取输出 txt
            txt_path = wav_path.replace(".wav", ".txt")
            if os.path.isfile(txt_path):
                with open(txt_path, "r", encoding="utf-8") as f:
                    text = f.read().strip()
                try:
                    os.remove(txt_path)
                except OSError:
                    pass
                return text if text else None

            return None

        except subprocess.TimeoutExpired:
            txt_path = wav_path.replace(".wav", ".txt")
            for p in (wav_path, txt_path):
                try:
                    os.remove(p)
                except OSError:
                    pass
            print('[voice] whisper.cpp 超时', flush=True)
            return None
        except Exception as e:
            print(f'[voice] whisper.cpp 失败: {e}', flush=True)
            return None

    # ==================== 第三层：faster-whisper ====================

    def _recognize_local(self, audio, sample_rate) -> str:
        """本地 faster-whisper 识别。"""
        if not self.whisper:
            return ""
        try:
            if sample_rate != 16000:
                audio = self._resample(audio, sample_rate, 16000)
            segments, _ = self.whisper.transcribe(
                audio,
                beam_size=5,
                language="zh",
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500, speech_pad_ms=200),
            )
            texts = [seg.text.strip() for seg in segments if seg.text.strip()]
            return " ".join(texts) if texts else ""
        except Exception as e:
            print(f'[voice] 本地识别失败: {e}', flush=True)
            return ""

    # ==================== 音频工具 ====================

    # ==================== 音频工具 ====================

    @staticmethod
    def _encode_wav(audio: np.ndarray, sample_rate: int) -> bytes:
        """float32 音频 → WAV bytes（PCM 16bit 单声道）。"""
        pcm = np.clip(audio, -1.0, 1.0) * 32767
        pcm = pcm.astype("<h").tobytes()
        import struct
        header = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF", 36 + len(pcm),
            b"WAVE", b"fmt ",
            16, 1, 1, sample_rate, sample_rate * 2, 2, 16,
            b"data", len(pcm),
        )
        return header + pcm

    def _audio_to_wav(self, audio: np.ndarray, sample_rate: int) -> bytes:
        """float32 音频 → WAV bytes（供 API 上传）。"""
        return self._encode_wav(audio, sample_rate)

    def _audio_to_wav_file(self, audio: np.ndarray, sample_rate: int) -> str:
        """float32 音频 → 临时 WAV 文件，返回路径。"""
        wav_bytes = self._encode_wav(audio, sample_rate)
        fd, path = tempfile.mkstemp(suffix=".wav")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(wav_bytes)
        except Exception:
            os.close(fd)
            raise
        return path

    def _resample(self, audio, orig_sr: int, target_sr: int):
        """简单降采样（线性插值）。"""
        ratio = orig_sr / target_sr
        indices = np.arange(0, len(audio), ratio)
        return np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)


# 兼容旧版 import 路径
import urllib.request
import json
import io as _io
