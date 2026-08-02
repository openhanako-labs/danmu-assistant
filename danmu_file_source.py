"""
弹幕源 - 文件监控
监控指定 txt 文件，新增行自动变成弹幕
"""
import time
import threading
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class DanmuFileHandler(FileSystemEventHandler):
    """文件变化事件处理器。"""
    def __init__(self, file_path, on_new_line):
        self.file_path = Path(file_path)
        self.on_new_line = on_new_line
        self._last_size = 0
        self._running = True
        self._paused = False

    def on_modified(self, event):
        if event.src_path != str(self.file_path):
            return
        if self._paused:
            return
        try:
            current_size = self.file_path.stat().st_size
            if current_size > self._last_size:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    f.seek(self._last_size)
                    new_lines = f.read().splitlines()
                    for line in new_lines:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            self.on_new_line(line)
                self._last_size = current_size
            elif current_size < self._last_size:
                # 文件被截断，从头读
                self._last_size = 0
        except Exception as e:
            print(f'[danmu-file] 读取失败: {e}', flush=True)


class DanmuFileSource:
    """文件监控弹幕源。"""
    def __init__(self, file_path: str = "danmu_source.txt"):
        self.file_path = file_path
        self.observer = Observer()
        self.handler = DanmuFileHandler(file_path, self._on_new_line)
        self.callbacks = []

    def _on_new_line(self, line):
        for cb in self.callbacks:
            cb(line)

    def on_danmu(self, callback):
        """注册弹幕回调。"""
        self.callbacks.append(callback)

    def start(self):
        """启动监控。"""
        # 初始化文件大小
        p = Path(self.file_path)
        if p.exists():
            self.handler._last_size = p.stat().st_size
        else:
            p.write_text('', encoding='utf-8')

        self.observer.schedule(self.handler, str(Path(self.file_path).parent), recursive=False)
        self.observer.start()
        print(f'[danmu-file] 监控文件: {self.file_path}', flush=True)

    def stop(self):
        self.observer.stop()
        self.observer.join()

    def set_paused(self, paused: bool):
        """暂停/恢复监控。"""
        self.handler._paused = paused
