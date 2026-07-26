"""
B站直播弹幕客户端 (blivedm_client)

通过 WebSocket 连接 B 站直播弹幕服务器：
    wss://broadcastlv.chat.bilibili.com:2245/sub

实现：
    - 房间号解析（短号 -> 真实 room_id）
    - 认证 (op=7)
    - 心跳保活 (op=2，默认 30s)
    - 弹幕协议解析（zlib / brotli 解压 + 分包）
    - DANMU_MSG 弹幕提取，通过回调喂给主弹幕系统

依赖：websockets

用法：
    client = BiliLiveClient(room_id=12345,
                            on_danmu=lambda text, source, user: add_danmu(text, source))
    client.start()   # 自带守护线程 + asyncio 事件循环
    ...
    client.stop()
"""
import struct
import zlib
import json
import asyncio
import threading
import logging
import urllib.request
import urllib.error

try:
    import websockets
except ImportError:  # pragma: no cover
    websockets = None

logger = logging.getLogger("blivedm")

# ============ 协议常量 ============
WSS_URL = "wss://broadcastlv.chat.bilibili.com:2245/sub"
# 16 字节头部：total_len(uint32) header_len(uint16) protover(uint16) op(uint32) seq(uint32)
HEADER = struct.Struct(">IHHII")

OP_HEARTBEAT = 2      # 客户端 -> 服务端：心跳
OP_HEARTBEAT_REPLY = 3  # 服务端 -> 客户端：人气值
OP_MESSAGE = 5        # 服务端 -> 客户端：普通消息（弹幕等）
OP_AUTH = 7           # 客户端 -> 服务端：认证
OP_AUTH_REPLY = 8     # 服务端 -> 客户端：认证回执

PROTO_JSON = 0        # 纯 JSON
PROTO_JSON_HEARTBEAT = 1  # 心跳回执 / 欢迎
PROTO_ZLIB = 2        # 包体 zlib 压缩
PROTO_BROTLI = 3      # 包体 brotli 压缩

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _pack(op: int, body: bytes) -> bytes:
    """构造一个数据包。"""
    header = HEADER.pack(16 + len(body), 16, 1, op, 1)
    return header + body


def _make_auth(room_id: int, uid: int = 0) -> bytes:
    """构造认证包。"""
    payload = json.dumps({
        "uid": uid,
        "roomid": room_id,
        "protover": 2,
        "platform": "web",
        "type": 2,
    }, separators=(",", ":")).encode("utf-8")
    return _pack(OP_AUTH, payload)


def _make_heartbeat() -> bytes:
    """构造心跳包（空包体）。"""
    return _pack(OP_HEARTBEAT, b"")


def _parse_packets(data: bytes):
    """解析收到的数据流，返回 [(op, body_bytes), ...]。

    处理 zlib / brotli 压缩包体：解压后的内容仍是多个子包，
    需要递归解析（B站会把多条弹幕打包进一个压缩包里）。
    """
    results = []
    pos = 0
    n = len(data)
    while pos + 16 <= n:
        total_len, header_len, protover, op, _seq = HEADER.unpack_from(data, pos)
        if total_len < 16 or pos + total_len > n:
            break
        body = data[pos + header_len: pos + total_len]
        pos += total_len

        if protover in (PROTO_ZLIB, PROTO_BROTLI):
            try:
                if protover == PROTO_ZLIB:
                    body = zlib.decompress(body)
                else:
                    import brotli
                    body = brotli.decompress(body)
                results.extend(_parse_packets(body))
            except Exception as e:
                logger.warning(f"[blivedm] 解压包体失败: {e}")
        else:
            # 纯 JSON（含心跳回执）
            results.append((op, body))
    return results


class BiliLiveClient:
    """B站直播弹幕客户端。"""

    def __init__(self, room_id, on_danmu=None, cookie: str = None,
                 uid: int = 0, wss_url: str = WSS_URL,
                 heartbeat_interval: float = 30.0):
        """
        :param room_id: 直播间号（短号或真实 room_id 均可）
        :param on_danmu: 回调 (text: str, source: str = "blivedm", user: str = None)
        :param cookie: 可选登录 Cookie（用于拉取需登录才能看的房间弹幕）
        :param uid: 用户 uid（0 为游客，给定 cookie 时可填真实 uid）
        :param wss_url: 弹幕服务器地址
        :param heartbeat_interval: 心跳间隔（秒）
        """
        self.room_id = int(room_id)
        self.cookie = cookie
        self.uid = int(uid)
        self.wss_url = wss_url
        self.heartbeat_interval = heartbeat_interval
        self.on_danmu = on_danmu

        self.running = False
        self._thread = None
        self._loop = None
        self._heartbeat_task = None
        self._real_room_id = None

    # ---------- 房间号解析 ----------
    def _resolve_room_id(self) -> int:
        """短号 -> 真实 room_id（失败则回退原始号）。"""
        url = f"https://api.live.bilibili.com/room/v1/Room/room_init?id={self.room_id}"
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": "https://live.bilibili.com",
            "Accept": "application/json",
        }
        if self.cookie:
            headers["Cookie"] = self.cookie
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("code") == 0:
                real = data.get("data", {}).get("room_id")
                if real:
                    return int(real)
        except urllib.error.URLError as e:
            logger.warning(f"[blivedm] 房间号解析失败，使用原始 id: {e}")
        except Exception as e:
            logger.warning(f"[blivedm] 房间号解析异常，使用原始 id: {e}")
        return self.room_id

    # ---------- 生命周期 ----------
    def start(self):
        if websockets is None:
            logger.error("[blivedm] 未安装 websockets，无法启动（pip install websockets）")
            return
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info(f"[blivedm] 客户端已启动，目标房间 {self.room_id}")

    def stop(self):
        self.running = False
        loop = self._loop
        if loop and loop.is_running():
            loop.call_soon_threadsafe(self._cancel)
        logger.info("[blivedm] 正在停止...")

    def _cancel(self):
        if self._heartbeat_task:
            self._heartbeat_task.cancel()

    def _run(self):
        if websockets is None:
            return
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        retry = 0
        try:
            while self.running:
                try:
                    self._loop.run_until_complete(self._connect())
                    retry = 0
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    retry += 1
                    wait = min(2 ** retry, 30)
                    logger.warning(f"[blivedm] 连接异常: {e}，{wait}s 后重连（第 {retry} 次）")
                    if not self.running:
                        break
                    self._loop.run_until_complete(asyncio.sleep(wait))
        finally:
            self._loop.close()
            logger.info("[blivedm] 客户端已停止")

    async def _connect(self):
        self._real_room_id = self._resolve_room_id()
        auth_packet = _make_auth(self._real_room_id, self.uid)
        headers = {
            "User-Agent": USER_AGENT,
            "Origin": "https://live.bilibili.com",
        }
        if self.cookie:
            headers["Cookie"] = self.cookie

        async with websockets.connect(
            self.wss_url,
            additional_headers=headers,
            ping_interval=None,   # 自己发心跳
            max_size=None,
        ) as ws:
            logger.info(f"[blivedm] 已连接 {self.wss_url}（房间 {self._real_room_id}）")
            await ws.send(auth_packet)
            logger.info("[blivedm] 已发送认证包")

            self._heartbeat_task = asyncio.ensure_future(self._heartbeat_loop(ws))

            try:
                async for raw in ws:
                    if not self.running:
                        break
                    if isinstance(raw, str):
                        raw = raw.encode("utf-8")
                    await self._dispatch(raw)
            finally:
                if self._heartbeat_task:
                    self._heartbeat_task.cancel()
                    try:
                        await self._heartbeat_task
                    except (asyncio.CancelledError, Exception):
                        pass
                logger.info("[blivedm] 连接已关闭")

    async def _heartbeat_loop(self, ws):
        try:
            while self.running:
                await asyncio.sleep(self.heartbeat_interval)
                if not self.running:
                    break
                await ws.send(_make_heartbeat())
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"[blivedm] 心跳异常: {e}")

    # ---------- 消息分发 ----------
    async def _dispatch(self, raw: bytes):
        for op, body in _parse_packets(raw):
            if op == OP_HEARTBEAT_REPLY:
                # 人气值（前 4 字节为 unsigned int）
                popularity = struct.unpack(">I", body[:4])[0] if len(body) >= 4 else 0
                logger.debug(f"[blivedm] 人气: {popularity}")
            elif op == OP_AUTH_REPLY:
                logger.info("[blivedm] 认证成功")
            elif op == OP_MESSAGE:
                try:
                    msg = json.loads(body.decode("utf-8"))
                except Exception:
                    continue
                self._handle_command(msg)

    def _handle_command(self, msg: dict):
        cmd = msg.get("cmd", "")
        # DANMU_MSG 可能有带后缀的变体，如 DANMU_MSG:4:0:2:2:2:0
        if cmd.startswith("DANMU_MSG"):
            self._handle_danmu(msg)
        elif cmd == "INTERACT_WORD":
            # 进入/关注/分享等互动，可选记录；这里仅日志
            logger.debug(f"[blivedm] 互动: {cmd}")
        elif cmd in ("ROOM_REAL_TIME_MESSAGE_UPDATE", "POPULARITY_RED_POCKET"):
            pass
        else:
            logger.debug(f"[blivedm] 其他cmd: {cmd}")

    def _handle_danmu(self, msg: dict):
        info = msg.get("info", [])
        if len(info) < 2:
            return
        text = info[1]
        user = ""
        if len(info) > 2 and isinstance(info[2], list) and len(info[2]) > 1:
            user = info[2][1]
        if not text:
            return
        logger.info(f'[blivedm] 弹幕 [{user}]: {text}')
        if self.on_danmu:
            try:
                self.on_danmu(text, source="blivedm", user=user)
            except Exception as e:
                logger.error(f"[blivedm] 回调异常: {e}")


if __name__ == "__main__":
    import time

    def _print(text, source="blivedm", user=None):
        print(f"[{source}] {user}: {text}")

    # 直接运行可测试：python blivedm_client.py
    import os
    rid = os.environ.get("ROOM_ID", "1")
    c = BiliLiveClient(room_id=rid, on_danmu=_print, cookie=os.environ.get("BILI_COOKIE"))
    c.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        c.stop()
