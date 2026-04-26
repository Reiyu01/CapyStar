import httpx
import websockets
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect,Response,UploadFile, File, Form
from fastapi.responses import StreamingResponse
import asyncio
from core.router import get_target, get_model_info
from auth.keygen import extract_key, decode_api_key
import os
import base64
import re
import struct

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

        if is_stream:
            async def event_stream():
                # 關鍵：在生成器內部開啟 client，確保串流期間它不會被關閉
                async with httpx.AsyncClient(timeout=120) as client:
                    async with client.stream("POST", target, json=body) as resp:
                        async for chunk in resp.aiter_text():
                            yield chunk
            return StreamingResponse(event_stream(), media_type="text/event-stream")

        else:
            # 非串流模式則維持原樣即可
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(target, json=body)
                return resp.json()

        # async with httpx.AsyncClient(timeout=120) as client:
        #     if is_stream:
        #         async def event_stream():
        #             async with client.stream("POST", target, json=body) as resp:
        #                 async for chunk in resp.aiter_text():
        #                     yield chunk
        #         return StreamingResponse(event_stream(), media_type="text/event-stream")

        #     else:
        #         resp = await client.post(target,json=body)
        #         return resp.json()
            
    #Websocket ASR路由邏輯 — 相容 OpenAI realtime 格式
    # OpenAI 標準: wss://.../v1/realtime?model=<model_name>
    # 同時保留 path param 格式向下相容
    @app.websocket("/v1/realtime")
    @app.websocket("/v1/realtime/{model_name}")
    # async def asr_websocket_proxy(websocket: WebSocket, model_name: str):
    #     # 1. 身份驗證 (從 Query Params 或 Headers 提取)
    #     api_key = websocket.query_params.get("api_key") or websocket.headers.get("Authorization")
    #     if api_key and api_key.startswith("Bearer "):
    #         api_key = api_key.replace("Bearer ", "")

    #     try:
    #         # 呼叫 keygen.py 中的 decode_api_key
    #         user = await decode_api_key(api_key, None) # 根據你之前的 decode_api_key 定義調整
    #         print(f">>> ASR 請求來自: {user['user_id']}")
    #     except Exception as e:
    #         print(f"ASR Auth Failed: {e}")
    #         await websocket.close(code=4003)
    #         return

    #     # 2. 定位後端服務 (Qwen3-ASR 跑在 8001 埠)
    #     raw_target = get_target(route_table, model_name)
    #     # 假設後端路徑是 /ws/asr
    #     target_base = raw_target.replace("/v1/chat/completions", "")
    #     target_ws_url = f"{target_base.replace('http', 'ws', 1).rstrip('/')}/ws/asr"

    #     print(f">>> 轉發 ASR 流量至: {target_ws_url}")

    #     await websocket.accept()

    #     try:
    #         # 3. 建立與 Qwen3-ASR 後端的連線
    #         async with websockets.connect(target_ws_url, ping_interval=20) as backend_ws:
                
    #             async def forward_to_backend():
    #                 """ 
    #                 前端 -> Proxy -> 後端 (Qwen3-ASR)
    #                 這部分會將前端傳來的二進位音訊或 JSON 指令原封不動丟給後端
    #                 """
    #                 async for message in websocket.iter_modules(): # 使用 iter_bytes/text 或通用 receive
    #                     data = await websocket.receive()
    #                     if "bytes" in data:
    #                         # Qwen3-ASR 預期收到 bytes 會進行 ASR 推論
    #                         await backend_ws.send(data["bytes"])
    #                     elif "text" in data:
    #                         # 處理前端傳來的控制指令 (例如: {"type": "control.finish_stream"})
    #                         await backend_ws.send(data["text"])
    #                     elif data["type"] == "websocket.disconnect":
    #                         break

    #             async def forward_to_client():
    #                 """ 
    #                 後端 (Qwen3-ASR) -> Proxy -> 前端
    #                 這裡會收到 Qwen3-ASR 回傳的 {"type": "response.streaming", "text": "..."}
    #                 """
    #                 async for message in backend_ws:
    #                     if isinstance(message, str):
    #                         # 轉發 Qwen3-ASR 的 JSON 結果給前端
    #                         await websocket.send_text(message)
    #                     else:
    #                         await websocket.send_bytes(message)

    #             # 雙向併發執行
    #             await asyncio.gather(forward_to_backend(), forward_to_client())

    #     except WebSocketDisconnect:
    #         print("Client disconnected from ASR Proxy")
    #     except Exception as e:
    #         print(f"ASR Proxy Error: {e}")
    #     finally:
    #         if websocket.client_state.name != "DISCONNECTED":
    #             await websocket.close()



    async def asr_websocket_proxy(websocket: WebSocket, model_name: str = None):
        # OpenAI 格式: ?model=<name>；舊格式: path param
        model_name = model_name or websocket.query_params.get("model", "qwen3-asr-1.7b")
        #連線驗證
        api_key = websocket.query_params.get("api_key") or websocket.headers.get("Authorization")

        if api_key and api_key.startswith("Bearer "):
            api_key = api_key.replace("Bearer ", "")
        try:
            user = decode_api_key(api_key)
            print(f">>> ASR 請求來自: {user['student_id']}")
        except Exception:
            # 必須先 accept 再 close，否則 WebSocket 會報錯
            await websocket.accept()
            await websocket.close(code=4003)
            return

        info = get_model_info(route_table, model_name)
        target_ws_url = info["base_url"].replace("http", "ws", 1) + "/v1/realtime"

        await websocket.accept()
        
        try:
            async with websockets.connect(target_ws_url, ping_interval=20) as backend_ws:

                async def forward_to_backend():
                    """前端(Pipecat) -> 後端(ASR) (音訊/指令)"""
                    audio_bytes_received = 0  # 🌟 新增：用來計算收到多少位元組的聲音
                    
                    while True:
                        data = await websocket.receive()
                        if "bytes" in data:
                            audio_chunk = data["bytes"]
                            audio_bytes_received += len(audio_chunk)
                            
                            # 🌟 新增：每收到約 16KB 的聲音（大約半秒），印出一次提示
                            if audio_bytes_received > 16000:
                                print(f"🟢 [ASR Proxy] 收到來自 Pipecat 的聲音封包! 已轉發 {audio_bytes_received} bytes")
                                audio_bytes_received = 0 # 歸零重新計算
                                
                            await backend_ws.send(audio_chunk)
                        elif "text" in data:
#                            print(f"📝 [ASR Proxy] 收到文字指令: {data['text']}")
                            await backend_ws.send(data["text"])
                        elif data["type"] == "websocket.disconnect":
                            print("❌ [ASR Proxy] Pipecat 斷開連線")
                            break


                # async def forward_to_backend():
                #     """前端 ->後端 (音訊/指令) """
                #     # 修正：使用 receive() 處理所有類型的 Frame
                #     while True:
                #         data = await websocket.receive()
                #         if "bytes" in data:
                #             await backend_ws.send(data["bytes"])
                #         elif "text" in data:
                #             await backend_ws.send(data["text"])
                #         elif data["type"] == "websocket.disconnect":
                #             break

                async def forward_to_client():
                    """後端 ->前端 (辨識結果) """

                    async for message in backend_ws:
                        #判斷類型

                        if isinstance(message, str):
                            await websocket.send_text(message)
                        else:
                            await websocket.send_bytes(message)

                #任一結束就全部停止
                done, pending = await asyncio.wait(
                    [
                        asyncio.create_task(forward_to_backend()),
                        asyncio.create_task(forward_to_client()),
                    ],
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


    # POST ASR — OpenAI 標準: POST /v1/audio/transcriptions (multipart/form-data)
    @app.post("/v1/audio/transcriptions")
    async def asr_proxy(request: Request):
        key = extract_key(request)
        user = decode_api_key(key)
        print(f">>> ASR 請求來自: {user['student_id']}")

        form = await request.form()
        model_name = form.get("model")
        response_format = form.get("response_format", "json")

        target = get_model_info(route_table, model_name)["url"]
        print(f">>> ASR 轉發目標: {target}")

        async with httpx.AsyncClient(timeout=60) as client:
            files = {}
            data = {}
            for k, v in form.items():
                if isinstance(v, UploadFile):
                    file_content = await v.read()
                    files[k] = (v.filename, file_content, v.content_type)
                else:
                    data[k] = v

            resp = await client.post(target, files=files, data=data)

            if resp.status_code != 200:
                return Response(content=resp.content, status_code=resp.status_code, media_type="application/json")

            # 統一回傳 OpenAI 格式: {"text": "..."}
            if response_format == "text":
                return Response(content=resp.content, media_type="text/plain")
            return Response(content=resp.content, status_code=200, media_type="application/json")

    @app.get("/v1/realtime/models")
    async def list_models():
        return {
            "object": "list",
            "data": [
                {"id": name, "object": "model", "owned_by": "system"}
                for name, info in route_table.items()
                if info["type"] == "asr"
            ]
        }


    # SSML 解析 (pipecat / Azure TTS 相容)
    def parse_ssml_to_fish_params(ssml_text: str):
        speed = float(re.search(r'rate="([\d\.]+)"', ssml_text).group(1)) \
            if re.search(r'rate="([\d\.]+)"', ssml_text) else None
        voice_match = re.search(r'name="([^"]+)"', ssml_text)
        voice_name = voice_match.group(1) if voice_match else None
        clean_text = re.sub(r'<[^>]*>', '', ssml_text).strip()
        return clean_text, voice_name, speed

    # response_format -> (Content-Type, Fish Speech 格式名)
    # Fish Speech 支援: wav/pcm, mp3, opus
    RESPONSE_FORMAT_MEDIA: dict = {
        "mp3":  "audio/mpeg",
        "opus": "audio/opus",
        "wav":  "audio/wav",
        "pcm":  "audio/pcm",   # 由 wav 產生後剝 header
    }

    # Fish Speech 各格式預設參數
    # wav/pcm: sample_rate 可選 8000/16000/24000/32000/44100，預設 24000 (pipecat 相容)
    # mp3:     sample_rate 可選 32000/44100，bitrate 64/128(預設)/192 kbps
    # opus:    sample_rate 固定 48000，bitrate -1000(auto)/24000/32000(預設)/48000/64000
    FORMAT_DEFAULTS: dict = {
        "wav":  {"sample_rate": 24000},
        "pcm":  {"sample_rate": 24000},
        "mp3":  {"sample_rate": 44100, "mp3_bitrate": 128},
        "opus": {"sample_rate": 48000, "opus_bitrate": 32000},
    }

    VOICE_DIR = "./voices"

    # TTS — OpenAI 標準: POST /v1/audio/speech
    # 同時保留 Fish Speech 原生路徑 /v1/tts
    # Request body: {model, input, voice, response_format?, speed?}
    @app.post("/v1/tts")
    @app.post("/v1/audio/speech")
    async def tts(request: Request):
        key = extract_key(request)
        user = decode_api_key(key)

        body = await request.json()

        # OpenAI 標準欄位: "input"；SSML / 舊版相容: "text"
        raw_input = body.get("input") or body.get("text", "")

        # 若輸入為 SSML，解析出文字/音色/語速；否則直接讀欄位
        if raw_input.lstrip().startswith("<"):
            clean_text, ssml_voice, ssml_speed = parse_ssml_to_fish_params(raw_input)
        else:
            clean_text, ssml_voice, ssml_speed = raw_input, None, None

        voice_name      = body.get("voice") or ssml_voice or "taiwan_girl"
        speed           = body.get("speed", ssml_speed if ssml_speed is not None else 1.0)
        response_format = body.get("response_format", "pcm")  # OpenAI 預設 mp3，pipecat 預設 pcm

        if response_format not in RESPONSE_FORMAT_MEDIA:
            return Response(
                content=f'{{"error": "不支援的格式 {response_format}，可選: {", ".join(RESPONSE_FORMAT_MEDIA)}"}}'.encode(),
                status_code=400,
                media_type="application/json",
            )

        if not clean_text:
            clean_text = raw_input

        # 找音色檔 (wav 優先 > mp3)，找不到 fallback
        def find_voice(name: str):
            for ext in ("wav", "mp3"):
                p = os.path.join(VOICE_DIR, f"{name}.{ext}")
                if os.path.exists(p):
                    return p
            return None

        voice_path = find_voice(voice_name)
        if not voice_path:
            fallback = "taiwan_girl"
            print(f"警告: 找不到音色 {voice_name}，切換至 {fallback}")
            voice_name = fallback
            voice_path = find_voice(voice_name)

        text_path = os.path.join(VOICE_DIR, f"{voice_name}.txt")

        references = []
        if voice_path:
            with open(voice_path, "rb") as f:
                audio_base64 = base64.b64encode(f.read()).decode("utf-8")
            ref_text = ""
            if os.path.exists(text_path):
                with open(text_path, "r", encoding="utf-8") as f:
                    ref_text = f.read().strip()
            references = [{"audio": audio_base64, "text": ref_text}]
        else:
            print(f"嚴重錯誤: 在 {VOICE_DIR} 中找不到任何音色檔。")

        # Fish Speech 不接受 "pcm" 格式名稱，用 wav 產生後自行剝 header
        fish_fmt = "wav" if response_format == "pcm" else response_format
        fmt_defaults = FORMAT_DEFAULTS.get(fish_fmt, {})

        payload = {
            "text":        clean_text,
            "references":  references,
            "format":      fish_fmt,
            "sample_rate": body.get("sample_rate", fmt_defaults.get("sample_rate")),
            "normalize":   True,
            "latency":     body.get("latency", "normal"),
            "prosody": {
                "speed":  speed,
                "volume": body.get("volume", 0),
            },
            "chunk_length":   body.get("chunk_length", 300),
            "temperature":    body.get("temperature", 0.7),
            "top_p":          body.get("top_p", 0.7),
            "seed":           body.get("seed", 42),
        }
        # 僅在對應格式時加入 bitrate 參數
        if "mp3_bitrate" in fmt_defaults:
            payload["mp3_bitrate"] = body.get("mp3_bitrate", fmt_defaults["mp3_bitrate"])
        if "opus_bitrate" in fmt_defaults:
            payload["opus_bitrate"] = body.get("opus_bitrate", fmt_defaults["opus_bitrate"])

        model_name = body.get("model", "")
        target = get_model_info(route_table, model_name)["url"]

        print(f">>> TTS | 音色: {voice_name} | 格式: {response_format} | 語速: {speed} | 內容: {clean_text[:30]}...")

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(target, json=payload)

            if resp.status_code != 200:
                print(f"後端報錯: {resp.text}")
                return Response(content=resp.text, status_code=resp.status_code, media_type="application/json")

            audio_content = resp.content
            # pcm 模式：掃描 RIFF chunk 找到 "data" 區塊再剝，避免額外 chunk 導致偶移
            if response_format == "pcm" and audio_content.startswith(b"RIFF"):
                actual_sr = struct.unpack_from("<I", audio_content, 24)[0]
                print(f">>> WAV sample_rate: {actual_sr}")
                # 掃描找 data chunk
                offset = 12
                pcm_data = audio_content[44:]  # fallback
                while offset + 8 <= len(audio_content):
                    tag  = audio_content[offset:offset + 4]
                    size = struct.unpack_from("<I", audio_content, offset + 4)[0]
                    if tag == b"data":
                        pcm_data = audio_content[offset + 8: offset + 8 + size]
                        break
                    offset += 8 + size
                audio_content = pcm_data

            media_type = RESPONSE_FORMAT_MEDIA.get(response_format, "audio/pcm")
            return Response(content=audio_content, media_type=media_type)





    #embedding處理
    @app.post("/v1/embeddings")
    async def embeddings_proxy(request: Request):
        # 1. 驗證 API KEY
        key = extract_key(request)
        user = decode_api_key(key)
        print(f">>> Embeddings 請求來自: {user['student_id']}")

        # 2. 解析 Request Body
        body = await request.json()
        model_name = body.get("model", "")
        
        # 3. 取得轉發目標
        target = get_model_info(route_table, model_name)["url"]
        
        print(f">>> 轉發 Embeddings 目標: {target}")

        # 4. 進行請求轉發
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(target, json=body)
            
            # 發生錯誤時回傳對應的 status_code
            if resp.status_code != 200:
                return Response(
                    content=resp.text, 
                    status_code=resp.status_code, 
                    media_type="application/json"
                )
            
            # 成功時回傳 JSON
            return resp.json()





        
    # VOICE_DIR = "./voices"
    # #於voices下放入對應wav檔以及txt以便讀取
