"""
空闲暂停监测器 — Windows GetLastInputInfo
检测用户无操作时间，超过阈值自动暂停弹幕，回来后自动恢复。
"""
import ctypes
import threading
import time
import logging

logger = logging.getLogger("idle")


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("dwTime", ctypes.c_uint),
    ]


def get_idle_seconds() -> float:
    """获取距上次用户输入（键鼠）的秒数。Windows only。"""
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
        tick = ctypes.windll.kernel32.GetTickCount()
        return (tick - lii.dwTime) / 1000.0
    return 0.0


class IdleMonitor:
    """空闲暂停监测器。"""

    def __init__(self, threshold_sec: int = 600):
        self.threshold = threshold_sec
        self.paused = False
        self.running = False
        self._thread = None
        self._lock = threading.Lock()

        self.on_pause = None
        self.on_resume = None

    def update_threshold(self, sec: int):
        with self._lock:
            self.threshold = sec
        logger.info(f"[idle] 空闲阈值已更新: {sec}s")

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info(f"[idle] 空闲监测已启动 (阈值: {self.threshold}s)")

    def stop(self):
        self.running = False

    def force_pause(self):
        with self._lock:
            if not self.paused:
                self.paused = True
                if self.on_pause:
                    self.on_pause()
                logger.info("[idle] 强制暂停")

    def force_resume(self):
        with self._lock:
            if self.paused:
                self.paused = False
                if self.on_resume:
                    self.on_resume()
                logger.info("[idle] 强制恢复")

    def _loop(self):
        while self.running:
            try:
                idle_sec = get_idle_seconds()
                with self._lock:
                    threshold = self.threshold
                    was_paused = self.paused

                should_pause = idle_sec > threshold
                if should_pause and not was_paused:
                    with self._lock:
                        self.paused = True
                    if self.on_pause:
                        self.on_pause()
                    logger.info(f"[idle] 无操作 {idle_sec:.0f}s > {threshold}s，暂停弹幕")
                elif not should_pause and was_paused:
                    with self._lock:
                        self.paused = False
                    if self.on_resume:
                        self.on_resume()
                    logger.info("[idle] 检测到操作，恢复弹幕")
            except Exception as e:
                logger.error(f"[idle] 检测异常: {e}")
            time.sleep(10)
