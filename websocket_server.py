"""
Phase 4 WebSocket 服务
- 广播弹幕实时推送
- 广播统计摘要
- 接收客户端指令（toggle / config 等）
"""
import asyncio
import json
import logging
import threading
import time
from datetime import datetime

logger = logging.getLogger("ws")

class WSServer:
    def __init__(self, port=8765, app_state=None):
        self.port = port
        self.app_state = app_state or {}
        self.clients = set()
        self._loop = None
        self._thread = None
        self._server = None

    async def _handler(self, ws):
        self.clients.add(ws)
        logger.info(f"WS client connected ({len(self.clients)} total)")
        try:
            async for msg in ws:
                try:
                    data = json.loads(msg)
                    await self._on_message(ws, data)
                except Exception as e:
                    logger.debug(f"WS msg error: {e}")
        finally:
            self.clients.discard(ws)
            logger.info(f"WS client disconnected ({len(self.clients)} total)")

    async def _on_message(self, ws, data):
        action = data.get("action")
        if action == "ping":
            await ws.send(json.dumps({"type": "pong", "ts": time.time()}))
        elif action == "status":
            ai = self.app_state.get("ai")
            voice = self.app_state.get("voice")
            config = self.app_state.get("config", {})
            await ws.send(json.dumps({
                "type": "status",
                "data": {
                    "running": bool(ai and ai.running),
                    "voice_enabled": bool(voice and voice.running),
                    "style": config.get("danmu_ai_style", "pi"),
                    "idle_paused": self.app_state.get("idle_paused", False),
                }
            }))
        else:
            await ws.send(json.dumps({"type": "error", "msg": "unknown action"}))

    async def _broadcast(self, payload):
        if not self.clients:
            return
        txt = json.dumps(payload, ensure_ascii=False)
        dead = []
        for ws in self.clients:
            try:
                await ws.send(txt)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    def broadcast_danmu(self, text, source="ai", emotion="neutral"):
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._broadcast({
                "type": "danmu",
                "text": text,
                "source": source,
                "emotion": emotion,
                "ts": time.time(),
            }), self._loop)

    def broadcast_stats(self, stats: dict):
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._broadcast({
                "type": "stats",
                "data": stats,
                "ts": time.time(),
            }), self._loop)

    async def _serve(self):
        import websockets
        self._server = await websockets.serve(self._handler, "0.0.0.0", self.port)
        logger.info(f"WS listening on :{self.port}")
        await asyncio.Future()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        def _run():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._serve())
        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def stop(self):
        if self._server and self._loop and self._loop.is_running():
            self._server.close()
            self._loop.call_soon_threadsafe(self._loop.stop)
