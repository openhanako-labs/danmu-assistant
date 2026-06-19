"""
弹幕统计面板 - 简化稳定版
"""
import time
from collections import Counter
from typing import Dict, List

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame,
    QGridLayout, QPushButton
)
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QColor


class DanmuStatsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint 
            | Qt.WindowType.Tool 
            | Qt.WindowType.WindowStaysOnTopHint
        )
        
        # 拖拽
        self.dragging = False
        self.drag_start = QPoint(0, 0)
        
        # 数据
        self.total_count = 0
        self.emotion_counts = Counter()
        self.word_counts = Counter()
        self.last_update = time.time()
        
        self._setup_ui()
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh)
        self.timer.start(1000)
    
    def _setup_ui(self):
        self.resize(220, 260)
        
        # 深色背景
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(20, 25, 40, 200);
                border-radius: 10px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        # 标题
        title = QLabel("📊 弹幕统计")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #E0E8FF; font-size: 14px; font-weight: bold; font-family: Microsoft YaHei;")
        layout.addWidget(title)
        
        # 密度
        self.density_label = QLabel("密度: 0 条/分")
        self.density_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.density_label.setStyleSheet("color: #A0B4FF; font-size: 12px; font-family: Microsoft YaHei;")
        layout.addWidget(self.density_label)
        
        # 情绪
        self.emotion_layout = QGridLayout()
        self.emotion_labels = {}
        for i, emo in enumerate(["兴奋", "开心", "惊讶", "悲伤", "愤怒", "中性"]):
            label = QLabel(f"{emo}: 0")
            label.setStyleSheet("color: #C0C8E0; font-size: 11px; font-family: Microsoft YaHei;")
            self.emotion_layout.addWidget(label, i // 2, i % 2)
            self.emotion_labels[emo.lower()] = label
        layout.addLayout(self.emotion_layout)
        
        # 高频词
        self.words_label = QLabel("高频词:\n(暂无)")
        self.words_label.setStyleSheet("color: #80A0FF; font-size: 11px; font-family: Microsoft YaHei;")
        layout.addWidget(self.words_label)
        
        # 关闭按钮
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet("""
            QPushButton {
                color: white; background: rgba(80,80,80,180); border: none; border-radius: 10px;
            }
            QPushButton:hover { background: rgba(200,50,50,200); }
        """)
        close_btn.clicked.connect(self.hide)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)
    
    def update_data(self, total, emotions, words):
        self.total_count = total
        self.emotion_counts = Counter(emotions)
        self.word_counts = Counter(dict(words))
        self.last_update = time.time()
        self._render()
    
    def _render(self):
        elapsed = time.time() - self.last_update
        density = self.total_count / (elapsed / 60) if self.total_count > 0 and elapsed > 0 else 0
        self.density_label.setText(f"密度: {density:.1f} 条/分")
        
        for emo, label in self.emotion_labels.items():
            label.setText(f"{emo.capitalize()}: {self.emotion_counts.get(emo, 0)}")
        
        top = self.word_counts.most_common(5)
        if top:
            self.words_label.setText("高频词:\n" + "\n".join(f"  {w}: {c}" for w, c in top))
        else:
            self.words_label.setText("高频词:\n(暂无)")
    
    def _refresh(self):
        if self.isVisible():
            self._render()
    
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
