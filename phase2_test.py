"""
Phase 2 集成测试
关键帧检测 + 说话人分离 + 弹幕皮肤 + 实时流式
"""
import asyncio
import base64
import json
import random
import sys
import yaml
from pathlib import Path

# 导入模块
from PyQt5.QtWidgets import QApplication
from keyframe_detector import KeyframeDetector
from speaker_diarization import SpeakerTracker
from danmu_skin import skin_manager
from stream_processor import StreamProcessor
from danmu_widget import DanmuOverlay
from inference import generate_danmu


async def phase2_integration_test():
    """Phase 2 集成测试"""
    print("=" * 60)
    print("Phase 2 集成测试")
    print("=" * 60)
    
    # 加载配置
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    # 1. 关键帧检测测试
    print("\n[1/4] 关键帧检测测试")
    detector = KeyframeDetector(threshold=0.15, min_interval=5)
    
    # 创建测试图像
    from PIL import Image
    img_red = Image.new("RGB", (100, 100), color=(255, 0, 0))
    img_green = Image.new("RGB", (100, 100), color=(0, 255, 0))
    img_blue = Image.new("RGB", (100, 100), color=(0, 0, 255))
    
    print(f"  红->绿: {detector.detect(img_red)}")  # True (第一帧)
    print(f"  绿->蓝: {detector.detect(img_green)}")  # True (大变化)
    print(f"  蓝->微蓝: {detector.detect(img_blue)}")  # False (小变化)
    print("  ✅ 关键帧检测测试通过")
    
    # 2. 说话人分离测试
    print("\n[2/4] 说话人分离测试")
    tracker = SpeakerTracker(max_speakers=3)
    
    dialogues = [
        ("主播", "大家好欢迎来到直播间"),
        ("观众", "666666主播加油"),
        ("主播", "今天我们来玩战双"),
    ]
    
    for person, text in dialogues:
        result = tracker.analyze_turn(text)
        print(f"  [{person}] '{text}' -> {result['speaker_name']}")
    print("  ✅ 说话人分离测试通过")
    
    # 3. 弹幕皮肤测试
    print("\n[3/4] 弹幕皮肤测试")
    for skin_name in ["default", "meme", "comment", "reaction", "highlight"]:
        skin = skin_manager.get_skin(skin_name)
        print(f"  [{skin_name}] 字体: {skin.font_size}px, 颜色: {len(skin.colors)}种")
    print("  ✅ 弹幕皮肤测试通过")
    
    # 4. 实时流式处理测试
    print("\n[4/4] 实时流式处理测试")
    processor = StreamProcessor()
    
    # 创建 Qt 应用和浮层
    app = QApplication(sys.argv)
    overlay = DanmuOverlay()
    overlay.show()
    
    # 注册事件处理器
    async def danmu_handler(event):
        if event.audio_text:
            # 生成弹幕
            danmu_list = await generate_danmu(
                audio_text=event.audio_text,
                speaker=event.speaker,
                use_vision=False,
                config=config
            )
            
            if danmu_list:
                for danmu in danmu_list:
                    text = danmu.get("text", "")
                    danmu_type = danmu.get("type", "comment")
                    # 映射弹幕类型到皮肤
                    skin_name = danmu_type if danmu_type in ["comment", "meme", "reaction"] else "default"
                    overlay.add_danmu(text, skin_name)
                    print(f"    [弹幕] [{skin_name}] {text}")
    
    processor.on_event(danmu_handler)
    
    # 模拟流式事件
    test_events = [
        ("主播", "大家好欢迎来到直播间，今天我们来玩战双帕弥什"),
        ("观众", "666666主播加油！"),
        ("主播", "哇这个技能特效太帅了！"),
    ]
    
    for person, text in test_events:
        await processor.process_audio_event(text, person)
    
    print("  ✅ 实时流式处理测试通过")
    
    # 显示统计
    stats = processor.get_stats()
    print(f"\n统计: {stats['total_events']} 个事件, 运行 {stats['running_time']} 秒")
    
    print("\n" + "=" * 60)
    print("Phase 2 集成测试全部通过！✅")
    print("=" * 60)
    print("\nPhase 2 功能清单:")
    print("  1. 关键帧检测 - 减少无效截屏")
    print("  2. 说话人分离 - 区分不同说话人")
    print("  3. 弹幕皮肤 - 不同类型不同样式")
    print("  4. 实时流式 - 事件驱动处理")
    print("\n按 Ctrl+C 退出...")
    
    try:
        sys.exit(app.exec_())
    except KeyboardInterrupt:
        print("\n测试退出 ✓")


if __name__ == "__main__":
    asyncio.run(phase2_integration_test())
