"""
共享画板 — WebSocket 服务器端
中继转发消息，不存储画布状态。
可部署到 Render.com（免费）等云平台。
"""

import asyncio
import os
import websockets

PORT = int(os.environ.get('PORT', 9999))
clients = {}


async def health_check(connection, request):
    """响应 Render.com / 其他平台的 HTTP 健康检查"""
    if request.path == '/':
        return connection.respond(200, 'OK')


async def handler(websocket):
    """处理单个客户端连接"""
    addr = websocket.remote_address
    clients[websocket] = addr
    print(f"[连接] {addr} 加入，当前在线 {len(clients)} 人")
    try:
        async for message in websocket:
            # 转发给所有其他客户端
            for c in list(clients):
                if c is not websocket:
                    await c.send(message)
    except websockets.ConnectionClosed:
        pass
    finally:
        del clients[websocket]
        print(f"[断开] {addr} 离开，当前在线 {len(clients)} 人")


async def main():
    async with websockets.serve(handler, '0.0.0.0', PORT,
                                process_request=health_check):
        print(f"WebSocket 服务器已启动，端口 {PORT}")
        await asyncio.Future()


if __name__ == '__main__':
    asyncio.run(main())
