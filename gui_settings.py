#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 弹幕助手 · GUI 设置面板 (PyQt6)

暗色卡片风格沿用 config_web.html：

  - 背景渐变:  #0f0c29 → #302b63 → #24243e
  - 卡片:      rgba(255,255,255,0.06) 背景, 1px 半透明白边, 12px 圆角
  - 主色:      #4facfe (主按钮渐变到 #00f2fe)
  - 文字:      #e0e0e0, 标签 #aaa, 字体 'Segoe UI'/'Microsoft YaHei'
  - 输入框:    rgba(0,0,0,0.3) 背景, 8px 圆角, 聚焦边框 #4facfe
  - API Key:   Consolas 等宽字体

Tab 布局：视觉模型 / 语音 / 弹幕行为 / B站直播
读取 config.yaml 填充表单，保存按钮写回 config.yaml。
"""

import os
import sys

import yaml
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")

# ---------------------------------------------------------------------------
# 暗色卡片风样式表（提取自 config_web.html）
# ---------------------------------------------------------------------------
STYLE = """
QWidget {
    font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
    color: #e0e0e0;
    font-size: 14px;
}
QDialog {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #0f0c29, stop:0.5 #302b63, stop:1 #24243e);
}
QLabel { color: #aaa; }
QLabel.header { color: #4facfe; font-size: 22px; font-weight: bold; }
QLabel.subtitle { color: #888; font-size: 13px; }

QGroupBox {
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 12px;
    padding: 16px;
    margin-top: 18px;
}
QGroupBox::title {
    color: #4facfe;
    font-size: 16px;
    subcontrol-position: top left;
    left: 14px;
    padding: 0 6px;
    background: transparent;
}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit {
    background: rgba(0,0,0,0.3);
    border: 1px solid rgba(255,255,255,0.15);
    border-radius: 8px;
    color: #e0e0e0;
    padding: 6px 10px;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QComboBox:focus, QTextEdit:focus {
    border: 1px solid #4facfe;
}
QTextEdit { font-family: 'Consolas', monospace; }

QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width: 16px; }

QComboBox QAbstractItemView {
    background: #24243e;
    color: #e0e0e0;
    selection-background-color: #4facfe;
    border: 1px solid rgba(255,255,255,0.15);
}

QCheckBox { color: #ccc; spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; }
QCheckBox::indicator:unchecked {
    border: 1px solid rgba(255,255,255,0.3);
    background: rgba(0,0,0,0.3);
    border-radius: 3px;
}
QCheckBox::indicator:checked {
    background: #4facfe;
    border-radius: 3px;
}

QSlider::groove:horizontal {
    background: rgba(255,255,255,0.15);
    height: 6px; border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #4facfe;
    border-radius: 9px;
    width: 18px;
    margin: -6px 0;
}

QTabWidget::pane { border: none; background: transparent; }
QTabBar::tab {
    background: rgba(255,255,255,0.06);
    color: #aaa;
    padding: 10px 18px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    margin-right: 4px;
}
QTabBar::tab:selected {
    background: rgba(79,172,254,0.2);
    color: #4facfe;
}

QScrollArea { border: none; background: transparent; }

QPushButton {
    border-radius: 10px;
    font-size: 15px;
    font-weight: bold;
    padding: 10px 24px;
}
QPushButton#primary {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #4facfe, stop:1 #00f2fe);
    color: #000;
}
QPushButton#secondary {
    background: rgba(255,255,255,0.1);
    color: #ccc;
    border: 1px solid rgba(255,255,255,0.15);
}
"""


# ---------------------------------------------------------------------------
# 配置读写辅助
# ---------------------------------------------------------------------------
def load_config(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}
    except yaml.YAMLError as e:
        raise ValueError(f"配置文件解析失败: {e}")


def get_path(cfg, path, default=None):
    cur = cfg
    for k in path:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return default
    return cur


def set_path(cfg, path, value):
    cur = cfg
    for k in path[:-1]:
        if not isinstance(cur.get(k), dict):
            cur[k] = {}
        cur = cur[k]
    cur[path[-1]] = value


# ---------------------------------------------------------------------------
# 设置对话框
# ---------------------------------------------------------------------------
class SettingsDialog(QDialog):
    def __init__(self, config_path=DEFAULT_CONFIG_PATH):
        super().__init__()
        self.config_path = config_path
        self.config = load_config(config_path)
        self.registry = []  # (path_tuple, widget, kind)
        self.special = {}   # 需要自定义转换的控件引用

        self.setWindowTitle("AI 弹幕助手 · 配置中心")
        self.resize(720, 660)
        self._build_ui()
        self._load_to_ui()

    # ----- UI 构建 -------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        # 标题
        header = QLabel("🎯 AI 弹幕助手")
        header.setProperty("class", "header")
        header.setStyleSheet("color:#4facfe;font-size:22px;font-weight:bold;")
        subtitle = QLabel("实时流式模式 · 配置保存在 config.yaml")
        subtitle.setStyleSheet("color:#888;font-size:13px;")
        root.addWidget(header)
        root.addWidget(subtitle)

        # Tab
        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        self._tab_vision = self._make_scroll_tab()
        self._tab_voice = self._make_scroll_tab()
        self._tab_danmu = self._make_scroll_tab()
        self._tab_bili = self._make_scroll_tab()

        tabs.addTab(self._tab_vision[0], "视觉模型")
        tabs.addTab(self._tab_voice[0], "语音")
        tabs.addTab(self._tab_danmu[0], "弹幕行为")
        tabs.addTab(self._tab_bili[0], "B站直播")

        self._build_vision(*self._tab_vision)
        self._build_voice(*self._tab_voice)
        self._build_danmu(*self._tab_danmu)
        self._build_bili(*self._tab_bili)

        # 按钮
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_save = QPushButton("💾 保存配置")
        btn_save.setObjectName("primary")
        btn_cancel = QPushButton("✖ 取消")
        btn_cancel.setObjectName("secondary")
        btn_save.clicked.connect(self.save_config)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_save, 1)
        btn_row.addWidget(btn_cancel, 1)
        root.addLayout(btn_row)

    def _make_scroll_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        scroll.setWidget(inner)
        return scroll, inner, layout

    # ----- 通用控件辅助 ---------------------------------------------------
    @staticmethod
    def _card(title):
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        layout.setSpacing(10)
        return box, layout

    def _add_row(self, layout, label_text, widget, label_width=150):
        row = QHBoxLayout()
        lbl = QLabel(label_text)
        lbl.setFixedWidth(label_width)
        row.addWidget(lbl)
        row.addWidget(widget, 1)
        layout.addLayout(row)
        return widget

    def _add_checkbox(self, layout, text, checked=False):
        cb = QCheckBox(text)
        cb.setChecked(checked)
        layout.addWidget(cb)
        return cb

    def _text(self, value="", password=False, mono=False):
        w = QLineEdit(str(value) if value is not None else "")
        if password:
            w.setEchoMode(QLineEdit.EchoMode.Password)
        if mono:
            w.setFont(QFont("Consolas"))
        return w

    def _int(self, value=0, minimum=0, maximum=999999):
        w = QSpinBox()
        w.setRange(minimum, maximum)
        w.setValue(int(value) if value is not None else minimum)
        return w

    def _float(self, value=0.0, minimum=0.0, maximum=10.0, step=0.1, decimals=2):
        w = QDoubleSpinBox()
        w.setRange(minimum, maximum)
        w.setSingleStep(step)
        w.setDecimals(decimals)
        w.setValue(float(value) if value is not None else minimum)
        return w

    def _choice(self, items, value=None):
        w = QComboBox()
        w.addItems(items)
        if value is not None and str(value) in items:
            w.setCurrentText(str(value))
        return w

    def _register(self, path, widget, kind):
        self.registry.append((path, widget, kind))

    # ----- Tab: 视觉模型 --------------------------------------------------
    def _build_vision(self, _scroll, _inner, layout):
        va = get_path(self.config, ("vision_api",), {})
        card, cl = self._card("🔑 视觉模型 API")
        layout.addWidget(card)

        w_provider = self._text(get_path(va, ("provider",)))
        self._add_row(cl, "Provider", w_provider)
        self._register(("vision_api", "provider"), w_provider, "text")

        w_url = self._text(get_path(va, ("base_url",)))
        self._add_row(cl, "Base URL", w_url)
        self._register(("vision_api", "base_url"), w_url, "text")

        w_model = self._text(get_path(va, ("model",)))
        self._add_row(cl, "Model", w_model)
        self._register(("vision_api", "model"), w_model, "text")

        w_key = self._text(get_path(va, ("api_key",)), password=True, mono=True)
        self._add_row(cl, "API Key", w_key)
        self._register(("vision_api", "api_key"), w_key, "password")

        layout.addStretch(1)

    # ----- Tab: 语音 ------------------------------------------------------
    def _build_voice(self, _scroll, _inner, layout):
        vc = get_path(self.config, ("voice",), {})

        card, cl = self._card("🎙️ 语音采集")
        layout.addWidget(card)
        w_enabled = self._add_checkbox(
            cl, "启用语音输入", bool(get_path(vc, ("enabled", False)))
        )
        self._register(("voice", "enabled"), w_enabled, "bool")

        self._add_row(
            cl, "采样率 (Hz)",
            self._reg(("voice", "sample_rate"),
                      self._int(get_path(vc, ("sample_rate", 48000), 8000, 192000), "int")))
        self._add_row(
            cl, "声道数",
            self._reg(("voice", "channels"),
                      self._int(get_path(vc, ("channels", 1), 1, 2), "int")))
        self._add_row(
            cl, "分块时长 (s)",
            self._reg(("voice", "chunk_duration"),
                      self._float(get_path(vc, ("chunk_duration", 1.5), 0.1, 10, 0.1, 1), "float")))
        self._add_row(
            cl, "静音阈值",
            self._reg(("voice", "silence_threshold"),
                      self._float(get_path(vc, ("silence_threshold", 0.01), 0, 0.1, 0.001, 3), "float")))
        self._add_row(
            cl, "最小语音占比",
            self._reg(("voice", "min_voice_ratio"),
                      self._float(get_path(vc, ("min_voice_ratio", 0.1), 0, 1, 0.01, 2), "float")))

        # ASR API
        asr = get_path(vc, ("asr_api",), {})
        card2, c2 = self._card("🌐 ASR API (远程识别)")
        layout.addWidget(card2)
        w_ap = self._text(get_path(asr, ("provider",)))
        self._add_row(c2, "Provider", w_ap)
        self._register(("voice", "asr_api", "provider"), w_ap, "text")
        w_au = self._text(get_path(asr, ("base_url",)))
        self._add_row(c2, "Base URL", w_au)
        self._register(("voice", "asr_api", "base_url"), w_au, "text")
        w_am = self._text(get_path(asr, ("model",)))
        self._add_row(c2, "Model", w_am)
        self._register(("voice", "asr_api", "model"), w_am, "text")
        w_ak = self._text(get_path(asr, ("api_key",)), password=True, mono=True)
        self._add_row(c2, "API Key", w_ak)
        self._register(("voice", "asr_api", "api_key"), w_ak, "password")

        # whisper.cpp
        wp = get_path(vc, ("whisper_cpp",), {})
        card3, c3 = self._card("⚙️ whisper.cpp (本地引擎)")
        layout.addWidget(card3)
        w_wen = self._add_checkbox(
            c3, "启用 whisper.cpp", bool(get_path(wp, ("enabled", False)))
        )
        self._register(("voice", "whisper_cpp", "enabled"), w_wen, "bool")
        w_exe = self._text(get_path(wp, ("exe_path",)))
        self._add_row(c3, "exe 路径", w_exe)
        self._register(("voice", "whisper_cpp", "exe_path"), w_exe, "text")
        w_mp = self._text(get_path(wp, ("model_path",)))
        self._add_row(c3, "模型路径", w_mp)
        self._register(("voice", "whisper_cpp", "model_path"), w_mp, "text")
        w_lang = self._text(get_path(wp, ("language", "zh")))
        self._add_row(c3, "语言", w_lang)
        self._register(("voice", "whisper_cpp", "language"), w_lang, "text")
        w_th = self._int(get_path(wp, ("threads", 4), 1, 32))
        self._add_row(c3, "线程数", w_th)
        self._register(("voice", "whisper_cpp", "threads"), w_th, "int")

        layout.addStretch(1)

    def _reg(self, path, widget, kind):
        """便捷注册：返回 widget 本身。"""
        self._register(path, widget, kind)
        return widget

    # ----- Tab: 弹幕行为 --------------------------------------------------
    def _build_danmu(self, _scroll, _inner, layout):
        dc = get_path(self.config, ("danmu",), {})

        card, cl = self._card("💬 弹幕生成")
        layout.addWidget(card)
        self._add_row(
            cl, "每次生成数量",
            self._reg(("danmu", "count"),
                      self._int(get_path(dc, ("count", 5), 1, 50), "int")))
        self._add_row(
            cl, "最大长度",
            self._reg(("danmu", "max_length"),
                      self._int(get_path(dc, ("max_length", 20), 1, 200), "int")))

        # available_styles -> 逗号文本；ai_style -> 下拉
        avail = get_path(dc, ("available_styles", [])) or []
        avail_items = [str(x) for x in avail] if avail else ["pi", "normal", "serious"]
        w_avail = self._text(", ".join(avail_items))
        self._add_row(cl, "可选风格 (逗号分隔)", w_avail)
        self.special["available_styles"] = w_avail

        ai_val = get_path(dc, ("ai_style", "pi"))
        w_ai = self._choice(avail_items, ai_val)
        self._add_row(cl, "初始风格", w_ai)
        self._register(("danmu", "ai_style"), w_ai, "choice")

        # 风格类型权重 (meme/comment/reaction)
        styles = get_path(dc, ("styles",), {}) or {}
        for key, val in styles.items():
            sb = self._float(val, 0, 1, 0.05, 2)
            self._add_row(cl, f"类型权重 · {key}", sb)
            self._register(("danmu", "styles", key), sb, "float")

        # AI 风格权重 (9 种)
        card2, c2 = self._card("🎲 AI 风格权重 (随机抽取)")
        layout.addWidget(card2)
        weights = get_path(dc, ("danmu_ai_style_weights",), {}) or {}
        if not weights:
            weights = {k: 1 for k in avail_items}
        for key, val in weights.items():
            sb = self._float(val, 0, 10, 0.1, 1)
            self._add_row(c2, key, sb)
            self._register(("danmu", "danmu_ai_style_weights", key), sb, "float")

        layout.addStretch(1)

    # ----- Tab: B站直播 ---------------------------------------------------
    def _build_bili(self, _scroll, _inner, layout):
        bc = get_path(self.config, ("blivedm",), {})

        card, cl = self._card("📺 B站直播弹幕源")
        layout.addWidget(card)
        w_enabled = self._add_checkbox(
            cl, "启用 B站直播弹幕", bool(get_path(bc, ("enabled", False)))
        )
        self._register(("blivedm", "enabled"), w_enabled, "bool")

        self._add_row(
            cl, "直播间号 (room_id)",
            self._reg(("blivedm", "room_id"),
                      self._int(get_path(bc, ("room_id", 1), 0, 99999999), "int")))

        w_cookie = QTextEdit()
        w_cookie.setPlainText(str(get_path(bc, ("cookie", "")) or ""))
        w_cookie.setMinimumHeight(90)
        self._add_row(cl, "登录 Cookie (可选)", w_cookie)
        self._register(("blivedm", "cookie"), w_cookie, "multiline")

        layout.addStretch(1)

    # ----- 加载 / 保存 ----------------------------------------------------
    def _load_to_ui(self):
        for path, widget, kind in self.registry:
            val = get_path(self.config, path)
            if val is None:
                continue
            if kind in ("text", "password"):
                widget.setText(str(val))
            elif kind == "int":
                widget.setValue(int(val))
            elif kind == "float":
                widget.setValue(float(val))
            elif kind == "bool":
                widget.setChecked(bool(val))
            elif kind == "multiline":
                widget.setPlainText(str(val))
            elif kind == "choice":
                widget.setCurrentText(str(val))

    def _collect_from_ui(self):
        for path, widget, kind in self.registry:
            if kind in ("text", "choice", "multiline"):
                set_path(self.config, path, widget.text().strip())
            elif kind == "password":
                txt = widget.text().strip()
                # 留空则不覆盖（避免误清空已存的 Key）
                if txt:
                    set_path(self.config, path, txt)
            elif kind == "int":
                set_path(self.config, path, widget.value())
            elif kind == "float":
                set_path(self.config, path, widget.value())
            elif kind == "bool":
                set_path(self.config, path, widget.isChecked())

        # available_styles: 逗号文本 -> 列表
        if "available_styles" in self.special:
            raw = self.special["available_styles"].text()
            items = [s.strip() for s in raw.split(",") if s.strip()]
            set_path(self.config, ("danmu", "available_styles"), items)

    def save_config(self):
        try:
            self._collect_from_ui()
            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(
                    self.config, f,
                    allow_unicode=True,
                    sort_keys=False,
                    default_flow_style=False,
                )
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "保存失败", str(e))
            return
        QMessageBox.information(self, "已保存", "配置已写入 config.yaml")
        self.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CONFIG_PATH
    dlg = SettingsDialog(path)
    dlg.exec()


if __name__ == "__main__":
    main()
