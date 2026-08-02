"""
端到端集成测试
截屏 → 视觉分析 → 弹幕生成 → Qt 浮层显示
"""
import asyncio
import httpx
import base64
import json
import sys
import random
import yaml
from pathlib import Path
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

# 导入模块
from danmu_widget import DanmuOverlay


async def test_end_to_end():
    """端到端测试"""
    # 加载配置
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    api_config = config["api"]
    
    # 读取测试图片
    img_path = "C:/Users/Administrator/.hanako/plugin-data/image-gen/generated/scene1-live-stream-a99a5721.jpg"
    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()
    
    # 创建 Qt 应用
    app = QApplication(sys.argv)
    overlay = DanmuOverlay()
    overlay.show()
    
    # 生成弹幕
    system_prompt = """你是B站直播间的老观众。请根据看到的画面生成5条弹幕：
- 弹幕要短、口语、带情绪
- 可以玩梗、吐槽、夸
- 不要解释、不要分析
- 用JSON格式：[{"text": "...", "type": "comment/meme/reaction"}]"""
    
    print("正在生成弹幕...")
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{api_config['endpoint']}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_config['api_key']}",
                "Content-Type": "application/json"
            },
            json={
                "model": api_config["model"],
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": [
                        {"type": "text", "text": "请根据这个场景生成弹幕"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                    ]}
                ],
                "temperature": 0.8,
                "max_tokens": 200
            }
        )
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        
        # 清理 markdown 代码块
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0] if "```" in content else content
        
        danmu_list = json.loads(content)
        print(f"\n✅ 生成 {len(danmu_list)} 条弹幕:")
        
        # 添加到浮层
        for i, danmu in enumerate(danmu_list, 1):
            text = danmu.get("text", "")
            danmu_type = danmu.get("type", "comment")
            color = random.choice(["#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7"])
            overlay.add_danmu(text, color, danmu_type)
            print(f"  {i}. [{danmu_type}] {text}")
        
        print("\n=== 端到端测试完成 ===")
        print("浮层已显示弹幕，等待手动关闭...")
        print("关闭窗口即退出")
        
        # 保持运行
        sys.exit(app.exec_())


if __name__ == "__main__":
    asyncio.run(test_end_to_end())
