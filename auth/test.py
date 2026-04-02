import websockets # 需要安裝: pip install websockets
from fastapi import WebSocket, WebSocketDisconnect

def register_proxy_routes(app: FastAPI, route_table: dict, config: dict):
    
    # ... 原有的 chat_completions 代碼 ...

    # 新增 WebSocket ASR 路由
    @app.websocket("/v1/asr/{model_name}")
    async def asr_websocket_proxy(websocket: WebSocket, model_name: str):
        # 1. 連線驗證 (可從 query param 或 header 提取 API Key)
        # 注意：瀏覽器原生 WebSocket API 不支援自定義 Header，通常透過 query string 傳遞
        api_key = websocket.query_params.get("api_key")
        try:
            user = decode_api_key(api_key)
            print(f">>> ASR 請求來自: {user['student_id']}")
        except Exception:
            await websocket.close(code=4003) # Forbidden
            return

        # 2. 獲取後端 A 機房的真實位址
        # 假設你的 route_table 裡 ASR 的位址是 http://... 改成 ws://...
        target_base = get_target(route_table, model_name)
        target_ws_url = target_base.replace("http://", "ws://").replace("/v1/chat/completions", "/ws")

        await websocket.accept()

        # 3. 雙向轉發 (Proxying)
        try:
            async with websockets.connect(target_ws_url) as backend_ws:
                # 定義兩個協程，分別處理「發送」與「接收」
                async def forward_to_backend():
                    async for message in websocket.iter_bytes(): # 接收前端傳來的音訊位元組
                        await backend_ws.send(message)

                async def forward_to_client():
                    async for message in backend_ws: # 接收 A 機房回傳的文字結果
                        await websocket.send_text(message)

                # 同時運行
                import asyncio
                await asyncio.gather(forward_to_backend(), forward_to_client())

        except WebSocketDisconnect:
            print("前端已斷開 WebSocket 連連")
        except Exception as e:
            print(f"ASR Proxy 錯誤: {e}")
            await websocket.close()



#v2


# 修改後的路由定義
@app.websocket("/v1/realtime/{model_name}")
async def asr_websocket_proxy(websocket: WebSocket, model_name: str):
    # 從 Query String 拿 API Key (OpenAI 規範在 WS 握手通常也是這樣做)
    api_key = websocket.query_params.get("api_key")
    
    try:
        # 驗證權限
        user = decode_api_key(api_key)
        print(f"Auth Success: {user['student_id']} calling {model_name}")
    except Exception:
        # 4003 代表 Unauthorized
        await websocket.close(code=4003) 
        return

    # 取得後端位址 (假設 config.yaml 裡配置了後端伺服器)
    target_url = get_target(route_table, model_name)
    # 轉換協議: http://140... -> ws://140...
    ws_target = target_url.replace("http://", "ws://").replace("/v1/chat/completions", "/ws/realtime")

    await websocket.accept()

    try:
        # 建立與 A 機房 (H200) 的長連接
        async with websockets.connect(ws_target) as backend_ws:
            
            # 轉發客戶端的音訊流到後端
            async def forward_audio():
                async for data in websocket.iter_bytes():
                    await backend_ws.send(data)

            # 轉發後端的文字結果到客戶端
            async def forward_text():
                async for response in backend_ws:
                    await websocket.send_text(response)

            await asyncio.gather(forward_audio(), forward_text())

    except WebSocketDisconnect:
        print("Client disconnected.")
    except Exception as e:
        print(f"Proxy Error: {e}")
    finally:
        if websocket.client_state.name != "DISCONNECTED":
            await websocket.close()

v3

import asyncio
import websockets
from fastapi import WebSocket, WebSocketDisconnect, HTTPException

async def asr_websocket_proxy(websocket: WebSocket, model_name: str):
    # 1. 驗證 (建議從 query_params 或 headers 同時嘗試)
    api_key = websocket.query_params.get("api_key") or websocket.headers.get("Authorization")
    try:
        user = decode_api_key(api_key)
    except Exception:
        await websocket.close(code=4003)
        return

    # 2. 取得後端位址
    target_base = get_target(route_table, model_name)
    target_ws_url = target_base.replace("http", "ws", 1) # 靈活替換協定

    await websocket.accept()

    try:
        # 增加 ping_interval 確保長連線不掉線
        async with websockets.connect(target_ws_url, ping_interval=20) as backend_ws:
            
            async def forward_to_backend():
                """前端 -> 後端 (音訊/指令)"""
                async for message in websocket.iter_modules(): # 使用通用疊代
                    # 根據資料類型轉發
                    data = message.get("bytes") or message.get("text")
                    if data:
                        await backend_ws.send(data)

            async def forward_to_client():
                """後端 -> 前端 (辨識結果)"""
                async for message in backend_ws:
                    # websockets 套件會自動判斷 str 或 bytes
                    if isinstance(message, str):
                        await websocket.send_text(message)
                    else:
                        await websocket.send_bytes(message)

            # 使用 wait 只要任一任務結束(斷線)就停止全部
            done, pending = await asyncio.wait(
                [forward_to_backend(), forward_to_client()],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()

    except WebSocketDisconnect:
        print("前端主動斷開")
    except Exception as e:
        print(f"ASR Proxy 異常: {e}")
    finally:
        # 確保狀態清理
        if websocket.client_state.name != "DISCONNECTED":
            await websocket.close()

