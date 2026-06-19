"""
Hanako WebSocket 联动模块
Phase 1: MVP 核心链路
"""
import json
import time
import asyncio
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict


@dataclass
class HanakoDanmuEvent:
    """
    Hanako 弹幕事件
    
    发送给 Hanako 的弹幕数据格式
    """
    type: str = "danmu"
    text: str = ""
    scene: Dict[str, Any] = None
    timestamp: float = 0.0
    
    def __post_init__(self):
        if self.scene is None:
            self.scene = {}
        if self.timestamp == 0.0:
            self.timestamp = time.time()
            
    def to_json(self) -> str:
        """序列化为 JSON 字符串"""
        return json.dumps(asdict(self), ensure_ascii=False)


class HanakoWebSocketClient:
    """
    Hanako WebSocket 客户端
    
    功能:
    - 发送弹幕事件到 Hanako
    - 接收 Hanako 的回应
    - 自动重连
    """
    
    def __init__(self, ws_url: str = "ws://localhost:18789", token: str = None):
        self.ws_url = ws_url
        self.token = token
        self.ws = None
        self.is_connected = False
        self.reconnect_delay = 1  # 初始重连延迟（秒）
        self.max_reconnect_delay = 30  # 最大重连延迟
        self.on_message_callback = None
        
    async def connect(self):
        """
        连接到 Hanako WebSocket 服务器
        
        Raises:
            ConnectionError: 连接失败
        """
        try:
            import websockets
            self.ws = await websockets.connect(
                self.ws_url,
                additional_headers={"Authorization": f"Bearer {self.token}"} if self.token else None
            )
            self.is_connected = True
            self.reconnect_delay = 1  # 重置重连延迟
            print(f"[Hanako] 已连接到 {self.ws_url}")
            return True
        except Exception as e:
            print(f"[Hanako] 连接失败: {e}")
            self.is_connected = False
            return False
            
    async def disconnect(self):
        """断开连接"""
        if self.ws:
            await self.ws.close()
            self.is_connected = False
            print("[Hanako] 已断开连接")
            
    async def send_danmu(self, danmu_text: str, scene: Dict[str, Any] = None):
        """
        发送弹幕事件到 Hanako
        
        Args:
            danmu_text: 弹幕文本
            scene: 场景数据（可选）
        """
        if not self.is_connected:
            print("[Hanako] 未连接，尝试重连...")
            await self.connect()
            if not self.is_connected:
                print("[Hanako] 重连失败，跳过发送")
                return
                
        event = HanakoDanmuEvent(
            type="danmu",
            text=danmu_text,
            scene=scene or {},
            timestamp=time.time()
        )
        
        try:
            message = event.to_json()
            await self.ws.send(message)
            print(f"[Hanako] 发送弹幕: {danmu_text}")
            
            # 接收回应（如果有）
            try:
                response = await asyncio.wait_for(self.ws.recv(), timeout=2.0)
                print(f"[Hanako] 收到回应: {response}")
            except asyncio.TimeoutError:
                pass  # 没有回应是正常的
                
        except Exception as e:
            print(f"[Hanako] 发送失败: {e}")
            self.is_connected = False
            
    async def send_batch_danmu(self, danmu_list: list, scene: Dict[str, Any] = None):
        """
        批量发送弹幕事件
        
        Args:
            danmu_list: 弹幕文本列表
            scene: 场景数据（可选）
        """
        for danmu_text in danmu_list:
            await self.send_danmu(danmu_text, scene)
            await asyncio.sleep(0.5)  # 每条弹幕间隔 0.5 秒
            
    async def listen(self):
        """
        监听 Hanako 消息
        
        持续接收来自 Hanako 的消息
        """
        if not self.is_connected:
            await self.connect()
            
        try:
            async for message in self.ws:
                data = json.loads(message)
                print(f"[Hanako] 收到消息: {data}")
                
                if self.on_message_callback:
                    await self.on_message_callback(data)
                    
        except Exception as e:
            print(f"[Hanako] 监听失败: {e}")
            self.is_connected = False
            
    async def reconnect_loop(self):
        """
        重连循环
        
        定期检查连接状态，断线后自动重连
        """
        while True:
            if not self.is_connected:
                print(f"[Hanako] 尝试重连 ({self.reconnect_delay}s)...")
                await asyncio.sleep(self.reconnect_delay)
                await self.connect()
                
                # 指数退避
                self.reconnect_delay = min(
                    self.reconnect_delay * 2,
                    self.max_reconnect_delay
                )
            else:
                self.reconnect_delay = 1  # 连接成功，重置延迟
                await asyncio.sleep(1)  # 每秒检查一次


class PetEventLink:
    """
    桌宠事件接口
    
    根据弹幕类型触发不同桌宠反应
    """
    
    def __init__(self, pet_api_url: str = "http://localhost:8080/api/pet"):
        self.pet_api_url = pet_api_url
        self.reactions = {
            "meme": "nod",           # 玩梗 → 点头
            "comment": "surprised",  # 评论 → 惊讶
            "reaction": "laugh",     # 反应 → 笑
            "scary": "hide",         # 害怕 → 缩起来
            "default": "idle"        # 默认 → 待机
        }
        
    async def trigger_pet_reaction(self, danmu_type: str, danmu_text: str):
        """
        触发表宠反应
        
        Args:
            danmu_type: 弹幕类型（meme/comment/reaction）
            danmu_text: 弹幕文本
        """
        action = self.reactions.get(danmu_type, self.reactions["default"])
        
        payload = {
            "action": action,
            "text": danmu_text,
            "timestamp": time.time()
        }
        
        print(f"[桌宠] 触发反应: {action} (弹幕类型: {danmu_type})")
        print(f"[桌宠] 文本: {danmu_text}")
        
        # 实际项目中会发送 HTTP 请求到桌宠 API
        # import httpx
        # async with httpx.AsyncClient() as client:
        #     await client.post(self.pet_api_url, json=payload)


# 测试代码
if __name__ == "__main__":
    print("=== Hanako WebSocket 联动模块测试 ===")
    print("\n模块结构:")
    print("  HanakoWebSocketClient - WebSocket 客户端")
    print("  HanakoDanmuEvent - 弹幕事件数据类")
    print("  PetEventLink - 桌宠事件接口")
    print("\n配置:")
    print("  ws_url: ws://localhost:18789")
    print("  token: 可选的 Bearer Token")
    print("\n功能:")
    print("  - 发送弹幕事件")
    print("  - 接收 Hanako 回应")
    print("  - 自动重连")
    print("  - 批量发送")
    print("\n依赖安装:")
    print("  pip install websockets")
    print("\nHanako 联动模块骨架代码已完成 ✓")
