"""
LLM 推理模块 - 基于 Prompt 生成弹幕
Phase 2: 支持关键帧检测 + 说话人分离 + 弹幕皮肤 + 实时流式
"""
import sys
import httpx
import json
import yaml
from pathlib import Path


# 加载配置
def load_config() -> dict:
    # PyInstaller 单文件模式下，__file__ 指向临时解压目录
    # 普通运行模式下指向项目目录
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
    config_path = base / "config.yaml"
    if not config_path.exists():
        # 回退：尝试当前工作目录
        config_path = Path("config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# Prompt 模板
SYSTEM_PROMPT_V2 = """
你是B站直播间的老观众。你正在观看一个电脑屏幕的画面：

【画面描述】{image_description}
【音频内容】{audio_text}
【说话人】{speaker}

请基于这个电脑屏幕画面生成{count}条弹幕。记住：
- 你是真实观众，不是AI助手
- 弹幕要短、要口语、要带情绪
- 可以玩梗，可以吐槽，可以夸
- 不要解释、不要分析、不要说"这个画面..."
- 不要生成与画面无关的内容
- 如果是代码编辑器，可以说"主播在写代码"
- 如果是浏览器，可以说"主播在看网页"
- 如果是游戏，可以说"主播在打游戏"
- 如果是桌面，可以说"主播桌面好干净/好乱"
- 不要每条都结构相似
- 用JSON格式返回：[{{"text": "...", "type": "comment/meme/reaction"}}]
"""


async def generate_danmu(
    image_base64: str = "",
    audio_text: str = "",
    speaker: str = "",
    prompt_version: str = "v2",
    config: dict = None,
    use_vision: bool = True,
    scene_description: str = ""
) -> list:
    """
    生成弹幕
    
    Args:
        image_base64: 图片的 base64 字符串（视觉模式使用）
        audio_text: 音频转写文本
        speaker: 说话人
        prompt_version: Prompt 版本
        config: 配置字典
        use_vision: 是否使用视觉模型
        scene_description: 画面描述（非视觉模式使用）
        
    Returns:
        弹幕列表，格式：[{"text": "...", "type": "..."}]
    """
    if config is None:
        config = load_config()
    
    api_config = config["api"]
    
    # 构建画面描述
    if scene_description:
        image_desc = scene_description
    elif use_vision and image_base64:
        image_desc = "（请根据图片描述画面内容）"
    else:
        image_desc = "（无画面信息）"
    
    # 构建 Prompt
    system_prompt = SYSTEM_PROMPT_V2.format(
        image_description=image_desc,
        audio_text=audio_text or "（无音频）",
        speaker=speaker or "（未知）",
        count=config["danmu"]["count"],
        max_length=config["danmu"]["max_length"]
    )
    
    # 构建消息
    if use_vision and image_base64:
        # 视觉模式：图片 + 文本
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": [
                {"type": "text", "text": "请根据这个场景生成弹幕"},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
                }
            ]}
        ]
        model = api_config.get("vision_model", api_config["model"])
    else:
        # 文本模式
        user_text = "请根据以下信息生成弹幕："
        if audio_text:
            user_text += f"\n音频: {audio_text}"
        if speaker:
            user_text += f"\n说话人: {speaker}"
        user_text += f"\n画面: {image_desc}"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text}
        ]
        model = api_config["model"]
    
    # 调用 LLM
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{api_config['endpoint']}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_config['api_key']}",
                "Content-Type": "application/json"
            },
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.8,
                "max_tokens": 200
            }
        )
        response.raise_for_status()
        data = response.json()
    
    # 解析结果
    try:
        content = data["choices"][0]["message"]["content"]
        # 清理 markdown 代码块
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0] if "```" in content else content
        danmu_list = json.loads(content)
        return danmu_list
    except Exception as e:
        print(f"解析弹幕失败: {e}")
        print(f"原始响应: {content}")
        return []


if __name__ == "__main__":
    # 测试 Prompt 模板
    print("=== Prompt V2 ===")
    print(SYSTEM_PROMPT_V2.format(
        image_description="测试画面",
        audio_text="测试音频",
        speaker="测试说话人",
        count=5,
        max_length=20
    ))
    print("\nPrompt 模板测试通过 ✓")
