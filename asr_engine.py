"""
ASR 引擎抽象层
三种实现：远程 API / whisper.cpp / faster-whisper
"""
from abc import ABC, abstractmethod
import numpy as np


class ASREngine(ABC):
    """ASR 识别引擎统一接口。"""

    @abstractmethod
    def recognize(self, audio: np.ndarray, sample_rate: int) -> str:
        """识别音频，返回文字。空字符串表示识别失败。"""
        pass


class ApiASREngine(ASREngine):
    """远程 ASR API（stepfun / openai / siliconflow）。"""

    def __init__(self, config: dict):
        self.config = config
        self.provider = config.get("provider", "")
        self.base_url = config.get("base_url", "")
        self.api_key = config.get("api_key", "")
        self.model = config.get("model", "whisper-1")

    def recognize(self, audio: np.ndarray, sample_rate: int) -> str:
        try:
            import urllib.request
            import json

            wav_bytes = _encode_wav(audio, sample_rate)
            boundary = "----DanmuBoundary"

            if self.provider in ("openai", "stepfun"):
                url = f"{self.base_url}/audio/transcriptions"
                body = (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n'
                    f"Content-Type: audio/wav\r\n\r\n"
                ).encode() + wav_bytes + (
                    f"\r\n--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="model"\r\n\r\n'
                    f"{self.model}\r\n--{boundary}--\r\n"
                ).encode()
                headers = {
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "Authorization": f"Bearer {self.api_key}",
                }
                req = urllib.request.Request(url, data=body, headers=headers, method="POST")

            elif self.provider == "siliconflow":
                url = f"{self.base_url}/audio/transcriptions"
                body = (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n'
                    f"Content-Type: audio/wav\r\n\r\n"
                ).encode() + wav_bytes + (
                    f"\r\n--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="model"\r\n\r\n'
                    f"{self.model}\r\n--{boundary}--\r\n"
                ).encode()
                headers = {
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "Authorization": f"Bearer {self.api_key}",
                }
                req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            else:
                return ""

            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            return result.get("text", "").strip()

        except Exception as e:
            print(f'[asr-api] 调用失败: {e}', flush=True)
            return ""


class CppASREngine(ASREngine):
    """whisper.cpp 本地引擎。"""

    def __init__(self, exe_path: str, model_path: str, language: str = "zh", threads: int = 4):
        self.exe_path = exe_path
        self.model_path = model_path
        self.language = language
        self.threads = threads

    def recognize(self, audio: np.ndarray, sample_rate: int) -> str:
        try:
            import subprocess
            import os
            import tempfile

            wav_path = _audio_to_wav_file(audio, sample_rate)
            try:
                cmd = [
                    self.exe_path,
                    "--model", self.model_path,
                    "--language", self.language,
                    "--threads", str(self.threads),
                    "--file", wav_path,
                    "--output-txt",
                    "--output-file", wav_path.replace(".wav", ""),
                ]
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=15,
                    creationflags=subprocess.CREATE_NO_WINDOW if __import__('sys').platform == "win32" else 0,
                )
                if result.returncode != 0:
                    print(f'[asr-cpp] 错误: {result.stderr[:200]}', flush=True)
                    return ""

                txt_path = wav_path.replace(".wav", ".txt")
                if os.path.isfile(txt_path):
                    with open(txt_path, "r", encoding="utf-8") as f:
                        text = f.read().strip()
                    return text
                return ""
            finally:
                for p in (wav_path, wav_path.replace(".wav", ".txt")):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
        except subprocess.TimeoutExpired:
            print('[asr-cpp] 超时', flush=True)
            return ""
        except Exception as e:
            print(f'[asr-cpp] 失败: {e}', flush=True)
            return ""


class FasterWhisperEngine(ASREngine):
    """faster-whisper Python 引擎（fallback）。"""

    def __init__(self, model_size: str = "base", device: str = "cpu", compute_type: str = "int8"):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None

    def _ensure_model(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
                print(f'[asr-whisper] 加载模型: {self.model_size} ({self.device}/{self.compute_type})...', flush=True)
                self._model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)
                print('[asr-whisper] 加载完成', flush=True)
            except Exception as e:
                print(f'[asr-whisper] 加载失败: {e}', flush=True)
                raise

    def recognize(self, audio: np.ndarray, sample_rate: int) -> str:
        try:
            self._ensure_model()
            if sample_rate != 16000:
                audio = _resample(audio, sample_rate, 16000)
            segments, _ = self._model.transcribe(
                audio, beam_size=5, language="zh",
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500, speech_pad_ms=200),
            )
            texts = [s.text.strip() for s in segments if s.text.strip()]
            return " ".join(texts)
        except Exception as e:
            print(f'[asr-whisper] 识别失败: {e}', flush=True)
            return ""


# ==================== 公共工具函数 ====================

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


def _audio_to_wav_file(audio: np.ndarray, sample_rate: int) -> str:
    """float32 音频 → 临时 WAV 文件路径。"""
    wav_bytes = _encode_wav(audio, sample_rate)
    fd, path = __import__('tempfile').mkstemp(suffix=".wav")
    try:
        with __import__('os').fdopen(fd, "wb") as f:
            f.write(wav_bytes)
    except Exception:
        __import__('os').close(fd)
        raise
    return path


def _resample(audio, orig_sr: int, target_sr: int):
    """简单降采样（线性插值）。"""
    ratio = orig_sr / target_sr
    indices = np.arange(0, len(audio), ratio)
    return np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)
