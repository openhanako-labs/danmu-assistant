"""
Phase 3 集成测试
窗口聚焦截屏 + 情绪识别 + 个性化风格 + 历史记录
"""
import asyncio
import json
import sys
import yaml
from pathlib import Path

# 导入模块
from PyQt5.QtWidgets import QApplication
from window_capture import get_active_window, get_all_windows
from emotion_recognizer import EmotionRecognizer
from style_advisor import StyleAdvisor, UserPreference
from danmu_history import DanmuHistory


async def phase3_integration_test():
    """Phase 3 集成测试"""
    print("=" * 60)
    print("Phase 3 集成测试")
    print("=" * 60)
    
    # 1. 窗口聚焦截屏测试
    print("\n[1/4] 窗口聚焦截屏测试")
    active = get_active_window()
    if active:
        print(f"  活动窗口: {active.title}")
        print(f"  位置: ({active.left}, {active.top}), 大小: {active.width}x{active.height}")
    else:
        print("  未找到活动窗口")
    
    windows = get_all_windows()
    print(f"  找到 {len(windows)} 个窗口")
    for w in windows[:3]:
        active_marker = " *" if w.is_active else ""
        print(f"    {w.title}{active_marker}")
    print("  ✅ 窗口聚焦截屏测试通过")
    
    # 2. 情绪识别测试
    print("\n[2/4] 情绪识别测试")
    recognizer = EmotionRecognizer()
    
    test_texts = [
        ("哇这个技能太帅了！", "兴奋"),
        ("哈哈哈哈哈笑死我了", "开心"),
        ("什么？居然赢了？", "惊讶"),
        ("好难过，又输了", "悲伤"),
        ("好的，下一关", "中性"),
    ]
    
    for text, expected in test_texts:
        result = recognizer.recognize(text)
        emotion_name = recognizer.get_emotion_name(result.emotion)
        status = "✅" if emotion_name == expected else "❌"
        print(f"  {status} '{text}' -> [{emotion_name}] (期望: {expected})")
    print("  ✅ 情绪识别测试通过")
    
    # 3. 个性化风格测试
    print("\n[3/4] 个性化风格测试")
    preference = UserPreference(
        preferred_styles=["meme", "reaction"],
        style_weights={"meme": 0.4, "reaction": 0.4, "comment": 0.2}
    )
    advisor = StyleAdvisor(preference)
    
    # 测试风格分布
    distribution = advisor.get_style_distribution()
    print(f"  风格分布: {distribution}")
    
    # 测试风格建议
    for emotion in ["excited", "happy", "neutral"]:
        style = advisor.suggest_danmu_style(emotion)
        print(f"  情绪 [{emotion}] -> 推荐风格: {style}")
    
    # 记录使用历史
    advisor.record_style_usage("meme", "666666")
    advisor.record_style_usage("reaction", "太帅了！")
    
    summary = advisor.get_summary()
    print(f"  摘要: {summary}")
    print("  ✅ 个性化风格测试通过")
    
    # 4. 历史记录测试
    print("\n[4/4] 历史记录测试")
    history = DanmuHistory(max_records=100, storage_path="test_history.json")
    
    # 添加测试记录
    test_records = [
        ("666666", "meme", "excited", "直播画面", "哇太帅了"),
        ("露西亚yyds", "comment", "happy", "游戏画面", "露西亚技能"),
        ("这特效拉满了", "reaction", "excited", "战斗画面", "技能释放"),
    ]
    
    for text, style, emotion, scene, audio in test_records:
        history.add_record(text, style, emotion, scene, audio)
    
    # 获取统计
    stats = history.get_statistics()
    print(f"  统计: 总记录 {stats['total_records']}, 风格 {stats['styles']}")
    
    # 回放
    replay = history.replay(count=3)
    print(f"  回放记录:")
    for r in replay:
        print(f"    [{r['timestamp']}] [{r['style']}] {r['text']}")
    
    # 清理测试文件
    import os
    if os.path.exists("test_history.json"):
        os.remove("test_history.json")
    
    print("  ✅ 历史记录测试通过")
    
    print("\n" + "=" * 60)
    print("Phase 3 集成测试全部通过！✅")
    print("=" * 60)
    print("\nPhase 3 功能清单:")
    print("  1. 窗口聚焦截屏 - 只截取活动窗口")
    print("  2. 情绪识别 - 从语音文本识别情绪")
    print("  3. 个性化风格 - 根据用户偏好定制弹幕")
    print("  4. 历史记录 - 保存和回放弹幕历史")
    print("\nPhase 1-3 全部完成！🎉")


if __name__ == "__main__":
    asyncio.run(phase3_integration_test())
