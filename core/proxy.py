import httpx
import websockets
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect,Response
from fastapi.responses import StreamingResponse
import asyncio
from core.router import get_target
from auth.keygen import extract_key, decode_api_key

#TODO: 目前都是用print輸出log，後續搭配loggingg以及資料庫來做紀錄
def register_proxy_routes(app: FastAPI, route_table: dict, config:dict):
    
    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        #驗證 API KEY
        #這邊不呼叫auth/routes中的/check-key端點字音為避免再繞一圈，底層操作皆為相同，直接呼叫底層函式效果相同且更快
        key = extract_key(request)
        user = decode_api_key(key)

        print(f">>> 請求來自: {user['student_id']}")

        body = await request.json()
        is_stream = body.get("stream", False)
        target = get_target(route_table, body.get("model",""))
        print(f">>> 轉發目標: {target}")

        async with httpx.AsyncClient(timeout=120) as client:
            if is_stream:
                async def event_stream():
                    async with client.stream("POST", target, json=body) as resp:
                        async for chunk in resp.aiter_text():
                            yield chunk
                return StreamingResponse(event_stream(), media_type="text/event-stream")

            else:
                resp = await client.post(target,json=body)
                return resp.json()
            
    #Websocket ASR路由邏輯
    @app.websocket("/v1/realtime/{model_name}")
    async def asr_websocket_proxy(websocket: WebSocket, model_name: str):
        #連線驗證
        api_key = websocket.query_params.get("api_key") or websocket.headers.get("Authorization")
        try:
            user = decode_api_key(api_key)
            print(f">>> ASR 請求來自: {user['student_id']}")
        except Exception:
            await websocket.close(code=4003)
            return


        target_base = get_target(route_table, model_name)
        target_base = target_base.replace("/v1/chat/completions", "")
        target_ws_url = target_base.replace("http", "ws", 1) 

        await websocket.accept()
        
        try:
            async with websockets.connect(target_ws_url, ping_interval=20) as backend_ws:

                async def forward_to_backend():
                    """前端 ->後端 (音訊/指令) """
                    # 修正：使用 receive() 處理所有類型的 Frame
                    while True:
                        data = await websocket.receive()
                        if "bytes" in data:
                            await backend_ws.send(data["bytes"])
                        elif "text" in data:
                            await backend_ws.send(data["text"])
                        elif data["type"] == "websocket.disconnect":
                            break

                async def forward_to_client():
                    """後端 ->前端 (辨識結果) """

                    async for message in backend_ws:
                        #判斷類型

                        if isinstance(message, str):
                            await websocket.send_text(message)
                        else:
                            await websocket.send_bytes(message)

                #使用wait只要任一任務結束就斷線停止全部
                done, pending = await asyncio.wait(
                    [forward_to_backend(), forward_to_client()],
                    return_when=asyncio.FIRST_COMPLETED,
                    )
                for task in pending:
                    task.cancel()

        except WebSocketDisconnect:
            pass 
        except Exception as e:
            print(f"ASR Proxy Error: {e}")
        finally:
            if websocket.client_state.name != "DISCONNECTED":
                await websocket.close()

    #fish speech tts路由邏輯
    @app.post("/v1/tts")
    async def tts(request: Request):
        key = extract_key(request)
        user = decode_api_key(key)
        
        body = await request.json()

        
        # 格式對應轉換：OpenAI -> Fish 原生
        if "input" in body:
            body["text"] = body.pop("input")
        if "response_format" in body:
            body["format"] = body.pop("response_format")

        model_name = body.get("model", "") 

        raw_target = get_target(route_table, model_name)
        # 這裡建議先 print 出來確認 raw_target 是什麼
        print(f"DEBUG: raw_target = {raw_target}")

        target = raw_target.replace("/v1/chat/completions", "") # 先拔掉舊路徑
        target = f"{target}/v1/tts" # 再補上新路徑，確保中間只有一個 
        target = target.replace("//v1", "/v1")

        print(f">>> 請求目標: {target}")

        async with httpx.AsyncClient(timeout=120) as client:
            # 記得帶上 Header 轉發給後端
            resp = await client.post(
                target, 
                json=body, 
               #headers={"Authorization": f"Bearer {key}"} 
            )

            if resp.status_code != 200:
                return Response(content=resp.text, status_code=resp.status_code, media_type="application/json")

            return Response(
                content=resp.content,
                media_type=resp.headers.get("content-type", "audio/mpeg"),
                headers={"Content-Disposition": "attachment; filename=speech.mp3"}
            )