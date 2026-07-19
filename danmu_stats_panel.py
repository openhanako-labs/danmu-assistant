"""
弹幕统计面板 + 设置面板（合并版）
统计信息 + 风格/间隔/语音/空闲 设置，直接在面板里调。
"""
import time
import json
import urllib.request
from collections import Counter
from typing import Dict, List

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QGridLayout, QPushButton, QComboBox, QSpinBox, QCheckBox,
    QScrollArea, QLineEdit, QGroupBox
)
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QColor


# HTTP API 基础地址（默认，由 main.py 启动时可通过环境变量覆盖）
_API_BASE = "http://127.0.0.1:18900"


def _api_post(path: str, data: dict = None) -> dict:
    """调用引擎 HTTP API。"""
    try:
        url = f"{_API_BASE}{path}"
        body = json.dumps(data or {}).encode("utf-8")
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _api_get(path: str) -> dict:
    try:
        url = f"{_API_BASE}{path}"
        with urllib.request.urlopen(url, timeout=3) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}


class DanmuStatsPanel(QWidget):
    """统计 + 设置合并面板。"""

    STYLES = [
        ("pi", "🎮 玩梗/皮"),
        ("normal", "💬 自然随意"),
        ("serious", "📋 正经描述"),
        ("tucao", "😏 犀利吐槽"),
        ("kuakua", "🌸 真诚赞美"),
        ("wenyi", "🌙 文艺诗意"),
        ("shadiao", "🤪 沙雕无厘头"),
        ("lengyoumo", "😎 冷幽默"),
        ("fanquan", "💕 饭圈化"),
    ]

    def __init__(self, parent=None, api_port: int = 18900):
        super().__init__(parent)
        global _API_BASE
        _API_BASE = f"http://127.0.0.1:{api_port}"

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )

        self.dragging = False
        self.drag_start = QPoint(0, 0)

        # 统计数据
        self.total_count = 0
        self.emotion_counts = Counter()
        self.word_counts = Counter()
        self.start_time = time.time()
        self.last_update = time.time()

        # 设置面板展开状态
        self._settings_visible = False

        self._setup_ui()

        # 定时刷新统计
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh)
        self.timer.start(1000)

    def _setup_ui(self):
        self.resize(260, 300)
        self.setMinimumWidth(240)

        self.setStyleSheet("""
            QWidget {
                background-color: rgba(20, 25, 40, 220);
                border-radius: 10px;
                color: #C0C8E0;
                font-family: Microsoft YaHei, system-ui;
                font-size: 11px;
            }
            QLabel { background: transparent; }
            QPushButton {
                background: rgba(60, 65, 85, 180);
                color: #E0E8FF;
                border: 1px solid rgba(100, 110, 150, 100);
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: rgba(99, 102, 241, 150);
                border-color: rgba(99, 102, 241, 200);
            }
            QComboBox, QSpinBox, QLineEdit {
                background: rgba(40, 45, 65, 200);
                color: #E0E8FF;
                border: 1px solid rgba(80, 85, 110, 150);
                border-radius: 4px;
                padding: 3px 6px;
                font-size: 11px;
            }
            QComboBox:focus, QSpinBox:focus, QLineEdit:focus {
                border-color: #6366f1;
            }
            QComboBox::drop-down { border: none; width: 16px; }
            QComboBox QAbstractItemView {
                background: #1a1d2e;
                color: #E0E8FF;
                selection-background-color: #6366f1;
            }
            QCheckBox { background: transparent; color: #C0C8E0; spacing: 6px; }
            QCheckBox::indicator {
                width: 14px; height: 14px;
                border-radius: 3px;
                border: 1px solid rgba(100,110,150,150);
                background: rgba(40,45,65,200);
            }
            QCheckBox::indicator:checked {
                background: #6366f1;
                border-color: #6366f1;
            }
            QGroupBox {
                background: transparent;
                border: 1px solid rgba(80, 85, 110, 80);
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 14px;
                font-size: 11px;
                font-weight: bold;
                color: #A0B4FF;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 8, 10, 8)
        main_layout.setSpacing(6)

        # ── 标题栏 ──
        title_bar = QHBoxLayout()
        title = QLabel("📊 弹幕助手")
        title.setStyleSheet("color: #E0E8FF; font-size: 13px; font-weight: bold;")
        title_bar.addWidget(title)

        self.btn_settings = QPushButton("⚙️")
        self.btn_settings.setFixedSize(24, 24)
        self.btn_settings.setStyleSheet("""
            QPushButton { background: transparent; border: none; font-size: 14px; }
            QPushButton:hover { background: rgba(99,102,241,80); border-radius: 4px; }
        """)
        self.btn_settings.clicked.connect(self._toggle_settings)
        title_bar.addWidget(self.btn_settings)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet("""
            QPushButton { background: transparent; border: none; font-size: 14px; }
            QPushButton:hover { background: rgba(200,50,50,150); border-radius: 4px; }
        """)
        close_btn.clicked.connect(self.hide)
        title_bar.addWidget(close_btn)
        main_layout.addLayout(title_bar)

        # ── 统计区域 ──
        self.density_label = QLabel("密度: 0 条/分")
        self.density_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.density_label.setStyleSheet("color: #A0B4FF; font-size: 12px; font-weight: bold;")
        main_layout.addWidget(self.density_label)

        # 状态行
        self.status_label = QLabel("⏳ 启动中...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #808080; font-size: 10px;")
        main_layout.addWidget(self.status_label)

        # 情绪网格
        emotion_grid = QGridLayout()
        emotion_grid.setSpacing(4)
        self.emotion_labels = {}
        emotions = [("兴奋", "excited"), ("开心", "happy"), ("惊讶", "surprise"),
                     ("悲伤", "sad"), ("愤怒", "angry"), ("中性", "neutral")]
        for i, (cn, en) in enumerate(emotions):
            lbl = QLabel(f"{cn}: 0")
            lbl.setStyleSheet("color: #C0C8E0; font-size: 10px;")
            emotion_grid.addWidget(lbl, i // 3, i % 3)
            self.emotion_labels[en] = lbl
        main_layout.addLayout(emotion_grid)

        # 高频词
        self.words_label = QLabel("高频词: (暂无)")
        self.words_label.setStyleSheet("color: #80A0FF; font-size: 10px;")
        self.words_label.setWordWrap(True)
        main_layout.addWidget(self.words_label)

        # ── 设置区域（默认隐藏） ──
        self.settings_widget = QWidget()
        settings_layout = QVBoxLayout(self.settings_widget)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(6)

        # 风格
        style_group = QGroupBox("🎯 风格")
        sg_layout = QVBoxLayout(style_group)
        sg_layout.setContentsMargins(8, 10, 8, 8)
        self.style_combo = QComboBox()
        for sid, sname in self.STYLES:
            self.style_combo.addItem(sname, sid)
        self.style_combo.currentIndexChanged.connect(self._on_style_change)
        sg_layout.addWidget(self.style_combo)
        settings_layout.addWidget(style_group)

        # 截图间隔
        interval_group = QGroupBox("⏱ 截图间隔")
        ig_layout = QHBoxLayout(interval_group)
        ig_layout.setContentsMargins(8, 10, 8, 8)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(2, 300)
        self.interval_spin.setValue(8)
        self.interval_spin.setSuffix(" 秒")
        self.interval_spin.valueChanged.connect(self._on_interval_change)
        ig_layout.addWidget(self.interval_spin)
        settings_layout.addWidget(interval_group)

        # 语音
        voice_group = QGroupBox("🎤 语音弹幕")
        vg_layout = QVBoxLayout(voice_group)
        vg_layout.setContentsMargins(8, 10, 8, 8)
        self.voice_check = QCheckBox("启用语音弹幕")
        self.voice_check.stateChanged.connect(self._on_voice_toggle)
        vg_layout.addWidget(self.voice_check)
        settings_layout.addWidget(voice_group)

        # 空闲暂停
        idle_group = QGroupBox("💤 空闲暂停")
        idle_layout = QHBoxLayout(idle_group)
        idle_layout.setContentsMargins(8, 10, 8, 8)
        idle_layout.addWidget(QLabel("超时"))
        self.idle_spin = QSpinBox()
        self.idle_spin.setRange(60, 7200)
        self.idle_spin.setValue(600)
        self.idle_spin.setSuffix(" 秒")
        self.idle_spin.setSingleStep(60)
        self.idle_spin.valueChanged.connect(self._on_idle_change)
        idle_layout.addWidget(self.idle_spin)
        settings_layout.addWidget(idle_group)

        # 引擎控制
        ctrl_layout = QHBoxLayout()
        self.btn_toggle = QPushButton("⏸ 暂停")
        self.btn_toggle.clicked.connect(self._on_toggle_engine)
        ctrl_layout.addWidget(self.btn_toggle)
        settings_layout.addLayout(ctrl_layout)

        self.settings_widget.setVisible(False)
        main_layout.addWidget(self.settings_widget)

        # 首次加载设置值
        QTimer.singleShot(2000, self._load_current_config)

    def _toggle_settings(self):
        self._settings_visible = not self._settings_visible
        self.settings_widget.setVisible(self._settings_visible)
        self.btn_settings.setText("📊" if self._settings_visible else "⚙️")
        # 展开时刷新配置
        if self._settings_visible:
            self._load_current_config()

    def _load_current_config(self):
        """从引擎读取当前配置并回显到控件。"""
        data = _api_get("/status")
        if "error" in data:
            self.status_label.setText("❌ 引擎未连接")
            return

        self.status_label.setText(
            f"{'🟢 运行中' if data.get('running') else '🔴 已停止'}"
            f" · 风格: {data.get('style', '?')}"
        )

        # 风格
        current_style = data.get("style", "pi")
        for i in range(self.style_combo.count()):
            if self.style_combo.itemData(i) == current_style:
                self.style_combo.setCurrentIndex(i)
                break

        # 语音
        self.voice_check.setChecked(data.get("voice_enabled", False))

        # 引擎状态
        if data.get("running"):
            self.btn_toggle.setText("⏸ 暂停引擎")
        else:
            self.btn_toggle.setText("▶ 启动引擎")

    def _on_style_change(self):
        style = self.style_combo.currentData()
        if style:
            _api_post("/style", {"style": style})

    def _on_interval_change(self, val):
        _api_post("/config/reload", {"capture_interval": val})

    def _on_voice_toggle(self, state):
        _api_post("/voice/toggle", {"enabled": bool(state)})

    def _on_idle_change(self, val):
        _api_post("/config/reload", {"idleThreshold": val})

    def _on_toggle_engine(self):
        data = _api_post("/toggle")
        if data.get("ok"):
            running = data.get("running", False)
            self.btn_toggle.setText("⏸ 暂停引擎" if running else "▶ 启动引擎")
            self.status_label.setText("🟢 运行中" if running else "🔴 已停止")

    # ── 统计数据更新（由 main.py 调用） ──

    def update_data(self, total, emotions, words):
        self.total_count = total
        self.emotion_counts = Counter(emotions)
        self.word_counts = Counter(dict(words))
        self.last_update = time.time()
        self._render()

    def _render(self):
        elapsed_min = (time.time() - self.start_time) / 60.0
        density = self.total_count / elapsed_min if self.total_count > 0 and elapsed_min > 0 else 0
        self.density_label.setText(f"密度: {density:.1f} 条/分")

        for emo, label in self.emotion_labels.items():
            label.setText(f"{'兴奋' if emo=='excited' else '开心' if emo=='happy' else '惊讶' if emo=='surprise' else '悲伤' if emo=='sad' else '愤怒' if emo=='angry' else '中性'}: {self.emotion_counts.get(emo, 0)}")

        top = self.word_counts.most_common(5)
        if top:
            self.words_label.setText("高频词: " + "  ".join(f"{w}({c})" for w, c in top))
        else:
            self.words_label.setText("高频词: (暂无)")

    def _refresh(self):
        if self.isVisible():
            self._render()

    # ── 拖拽 ──

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.drag_start = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.dragging and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_start)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            event.accept()
