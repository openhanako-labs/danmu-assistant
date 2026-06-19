"""
弹幕云词集成测试
集成：弹幕浮层 + 统计面板 + 情绪识别 + 历史记录
"""
import asyncio
import sys
import time
from collections import Counter

from PyQt5.QtWidgets import QApplication

from danmu_widget import DanmuOverlay
from danmu_stats_panel import DanmuStatsPanel
from emotion_recognizer import EmotionRecognizer
from danmu_history import DanmuHistory


async def cloud_word_integration_test():
    """弹幕云词集成测试"""
    print("=" * 60)
    print("弹幕云词集成测试")
    print("=" * 60)
    
    # 创建 Qt 应用
    app = QApplication(sys.argv)
    
    # 创建弹幕浮层和统计面板
    overlay = DanmuOverlay()
    overlay.show()
    
    panel = DanmuStatsPanel()
    panel.show()
    
    # 初始化模块
    recognizer = EmotionRecognizer()
    history = DanmuHistory(max_records=50, storage_path="cloud_test_history.json")
    
    # 模拟弹幕流
    test_danmus = [
        ("哇太帅了！", "meme", "excited"),
        ("666666", "meme", "excited"),
        ("露西亚 yyds", "reaction", "happy"),
        ("哈哈哈哈哈", "comment", "happy"),
        ("这特效拉满了", "reaction", "excited"),
        ("再来一波", "meme", "excited"),
        ("好难过", "comment", "sad"),
        ("气死了", "reaction", "angry"),
        ("哭哭", "comment", "sad"),
        ("无语", "reaction", "neutral"),
        ("太棒了！", "meme", "excited"),
        ("666", "meme", "excited"),
        ("露西亚老婆", "reaction", "happy"),
        ("太强了", "comment", "excited"),
        ("绝了", "meme", "excited"),
    ]
    
    print("\n模拟弹幕流:")
    for text, style, emotion in test_danmus:
        # 添加到浮层
        overlay.add_danmu(text, style)
        
        # 添加到历史记录
        history.add_record(text, style, emotion)
        
        # 更新统计面板
        recent = history.get_recent_records(15)
        total = len(recent)
        
        # 统计情绪
        emotions = {}
        for r in recent:
            emotions[r.emotion] = emotions.get(r.emotion, 0) + 1
        
        # 统计高频词
        words_counter = Counter()
        for r in recent:
            # 简单分词（按常见词）
            common_words = ["太帅了", "666", "露西亚", "yyds", "哈哈", "特效", "难过", "气死", "哭哭", "无语", "太强了", "绝了", "老婆"]
            for word in common_words:
                if word in r.text:
                    words_counter[word] += 1
        
        words = words_counter.most_common(5)
        panel.update_data(total, emotions, words)
        
        print(f"  [{style}] {text} (情绪: {emotion})")
        await asyncio.sleep(0.3)
    
    # 显示最终统计
    stats = history.get_statistics()
    print(f"\n最终统计:")
    print(f"  总记录: {stats['total_records']}")
    print(f"  风格分布: {stats['styles']}")
    print(f"  情绪分布: {stats['emotions']}")
    
    # 清理测试文件
    import os
    if os.path.exists("cloud_test_history.json"):
        os.remove("cloud_test_history.json")
    
    print("\n" + "=" * 60)
    print("弹幕云词集成测试完成！✅")
    print("=" * 60)
    print("\n按 Ctrl+C 退出...")
    
    try:
        sys.exit(app.exec_())
    except KeyboardInterrupt:
        print("\n测试退出 ✓")


if __name__ == "__main__":
    asyncio.run(cloud_word_integration_test())
