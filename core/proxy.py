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
import json as _json
import uuid

def _pcm16_to_wav(pcm_bytes: bytes, sample_rate: int = 24000, channels: int = 1) -> bytes:
    """將原始 PCM16 bytes 包成 WAV 容器（24kHz mono 預設）"""
    sample_width = 2  # 16-bit
    data_size = len(pcm_bytes)
    header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF', 36 + data_size, b'WAVE',
        b'fmt ', 16, 1, channels, sample_rate,
        sample_rate * channels * sample_width,
        channels * sample_width,
        sample_width * 8,
        b'data', data_size
    )
    return header + pcm_bytes


class _PCMAudioBuffer:
    """Pure-bytes PCM16 audio buffer.

    Accumulates raw PCM16 bytes and yields fixed-size segments for
    transcription. No numpy required — works directly with bytes.

    Parameters
    ----------
    sample_rate       : Audio sample rate in Hz (default 24000 to match OpenAI Realtime)
    segment_duration_s: How many seconds of audio to accumulate before auto-transcribing
    """
    def __init__(self, sample_rate: int = 24000, segment_duration_s: float = 5.0):
        # PCM16 = 2 bytes per sample
        self._segment_bytes = int(segment_duration_s * sample_rate * 2)
        self._buf = bytearray()

    def append(self, data: bytes) -> None:
        self._buf += data

    def read_segment(self) -> bytes | None:
        """Return one full segment (segment_duration_s) if available, else None."""
        if len(self._buf) < self._segment_bytes:
            return None
        segment = bytes(self._buf[:self._segment_bytes])
        del self._buf[:self._segment_bytes]
        return segment

    def flush(self) -> bytes | None:
        """Return all remaining bytes and clear the buffer."""
        if not self._buf:
            return None
        audio = bytes(self._buf)
        self._buf.clear()
        return audio

    def clear(self) -> None:
        self._buf.clear()

    def __len__(self) -> int:
        return len(self._buf)


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
        # 永遠用 base_url + /v1/chat/completions，不受模型 type 影響
        model_name = body.get("model", "")
        info   = get_model_info(route_table, model_name)
        target = info["base_url"] + "/v1/chat/completions"
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
            
    # ──────────────────────────────────────────────────────────────
    # WebSocket: /v1/realtime — 相容 OpenAI Realtime Transcription API
    # wss://.../v1/realtime?model=<model>
    # 支援事件: session.update / input_audio_buffer.append / .commit / .clear
    # 回傳事件: session.created / session.updated / input_audio_buffer.committed
    #           conversation.item.input_audio_transcription.delta / .completed / error
    #
    # 音訊緩衝策略:
    #   - 每累積 segment_duration_s 秒的 PCM16 音訊 → 自動送出辨識（不需要客戶端 commit）
    #   - 客戶端顯式 commit → 立即 flush 剩餘音訊並辨識
    # ──────────────────────────────────────────────────────────────
    @app.websocket("/v1/realtime")
    @app.websocket("/v1/realtime/{model_name}")
    async def realtime_transcription(websocket: WebSocket, model_name: str = None):
        # 1. 身份驗證
        api_key = websocket.query_params.get("api_key") or websocket.headers.get("Authorization", "")
        if api_key.startswith("Bearer "):
            api_key = api_key[7:]
        try:
            user = decode_api_key(api_key)
            print(f">>> Realtime ASR 請求來自: {user['student_id']}")
        except Exception:
            await websocket.accept()
            await websocket.close(code=4003)
            return

        # 2. 模型選擇（優先: path param > query param > 預設）
        model_name = model_name or websocket.query_params.get("model", "qwen3-asr-1.7b")

        await websocket.accept()

        # 3. Session 狀態
        session_id = uuid.uuid4().hex
        session_config = {
            "id": f"sess_{session_id[:8]}",
            "object": "realtime.session",
            "type": "transcription",
            "model": model_name,
            "audio": {
                "input": {
                    "format": {"type": "audio/pcm", "rate": 24000},
                    "transcription": {
                        "model": model_name,
                        "language": "zh",
                    },
                    "turn_detection": None,  # 停用 VAD，由客戶端 commit 或緩衝區自動切段
                }
            }
        }

        # 4. session.created
        await websocket.send_text(_json.dumps({
            "event_id": f"event_{uuid.uuid4().hex[:8]}",
            "type": "session.created",
            "session": session_config
        }))

        # 5. 音訊緩衝區（自動每 5 秒切一段）
        audio_buf  = _PCMAudioBuffer(sample_rate=24000, segment_duration_s=5.0)
        item_counter = 0
        prev_item_id: str | None = None

        async def _transcribe(item_id: str, pcm_bytes: bytes, lang: str) -> None:
            """PCM16 → WAV → POST 後端 → 發送 delta + completed 事件"""
            nonlocal prev_item_id
            wav_bytes = _pcm16_to_wav(pcm_bytes)
            info      = get_model_info(route_table, model_name)
            provider  = info.get("provider", "vllm")
            target    = (info["base_url"] + "/v1/audio/transcriptions") if provider == "vllm" else info["url"]
            print(f">>> Realtime ASR [{item_id}] 轉發: {target} ({len(pcm_bytes)} bytes PCM)")
            try:
                async with httpx.AsyncClient(timeout=120) as client:
                    resp = await client.post(
                        target,
                        files={"file": ("audio.wav", wav_bytes, "audio/wav")},
                        data={"model": model_name, "language": lang, "response_format": "json"}
                    )
                if resp.status_code == 200:
                    transcript = resp.json().get("text", "")
                    await websocket.send_text(_json.dumps({
                        "event_id": f"event_{uuid.uuid4().hex[:8]}",
                        "type": "conversation.item.input_audio_transcription.delta",
                        "item_id": item_id,
                        "content_index": 0,
                        "delta": transcript
                    }))
                    await websocket.send_text(_json.dumps({
                        "event_id": f"event_{uuid.uuid4().hex[:8]}",
                        "type": "conversation.item.input_audio_transcription.completed",
                        "item_id": item_id,
                        "content_index": 0,
                        "transcript": transcript
                    }))
                    print(f">>> Realtime ASR [{item_id}] 結果: {transcript}")
                    prev_item_id = item_id
                else:
                    raise RuntimeError(f"Backend {resp.status_code}: {resp.text[:200]}")
            except Exception as exc:
                print(f">>> Realtime ASR [{item_id}] 錯誤: {exc}")
                try:
                    await websocket.send_text(_json.dumps({
                        "event_id": f"event_{uuid.uuid4().hex[:8]}",
                        "type": "error",
                        "error": {"type": "transcription_error", "message": str(exc), "item_id": item_id}
                    }))
                except Exception:
                    pass

        def _next_item_id() -> str:
            nonlocal item_counter
            item_counter += 1
            return f"item_{item_counter:03d}"

        async def _commit_segment(pcm: bytes) -> None:
            """發 committed 事件 + 非同步啟動辨識任務"""
            item_id = _next_item_id()
            await websocket.send_text(_json.dumps({
                "event_id": f"event_{uuid.uuid4().hex[:8]}",
                "type": "input_audio_buffer.committed",
                "previous_item_id": prev_item_id,
                "item_id": item_id
            }))
            lang = session_config["audio"]["input"]["transcription"].get("language", "zh")
            asyncio.create_task(_transcribe(item_id, pcm, lang))

        # 6. 事件迴圈
        try:
            while True:
                data = await websocket.receive()
                if data["type"] == "websocket.disconnect":
                    break
                if "text" not in data:
                    continue
                try:
                    event = _json.loads(data["text"])
                except _json.JSONDecodeError:
                    continue

                etype = event.get("type", "")

                # ── session.update ──────────────────────────────
                if etype == "session.update":
                    update = event.get("session", {})
                    try:
                        lang_val = update["audio"]["input"]["transcription"]["language"]
                        session_config["audio"]["input"]["transcription"]["language"] = lang_val
                    except KeyError:
                        pass
                    if "model" in update:
                        session_config["model"] = model_name = update["model"]
                        session_config["audio"]["input"]["transcription"]["model"] = model_name
                    await websocket.send_text(_json.dumps({
                        "event_id": f"event_{uuid.uuid4().hex[:8]}",
                        "type": "session.updated",
                        "session": session_config
                    }))

                # ── input_audio_buffer.append ────────────────────
                elif etype == "input_audio_buffer.append":
                    b64 = event.get("audio", "")
                    if b64:
                        audio_buf.append(base64.b64decode(b64))
                        # 自動切段：每滿 5 秒就觸發一次辨識
                        while True:
                            seg = audio_buf.read_segment()
                            if seg is None:
                                break
                            await _commit_segment(seg)

                # ── input_audio_buffer.commit ────────────────────
                elif etype == "input_audio_buffer.commit":
                    remaining = audio_buf.flush()
                    if remaining:
                        await _commit_segment(remaining)

                # ── input_audio_buffer.clear ─────────────────────
                elif etype == "input_audio_buffer.clear":
                    audio_buf.clear()
                    await websocket.send_text(_json.dumps({
                        "event_id": f"event_{uuid.uuid4().hex[:8]}",
                        "type": "input_audio_buffer.cleared"
                    }))

        except WebSocketDisconnect:
            pass
        except Exception as e:
            print(f"Realtime Proxy Error: {e}")
        finally:
            try:
                if websocket.client_state.name != "DISCONNECTED":
                    await websocket.close()
            except Exception:
                pass

    # POST ASR — 同時支援 application/json 及 multipart/form-data
    # 若後端 provider=vllm，自動將請求轉換為 /v1/chat/completions + input_audio 格式
    @app.post("/v1/audio/transcriptions")
    async def asr_proxy(request: Request):
        # =========================
        # 0️⃣ 基本資訊
        # =========================
        key = extract_key(request)
        user = decode_api_key(key)
        print(f">>> ASR 請求來自: {user.get('student_id')}")

        content_type = request.headers.get("content-type", "")
        print(f">>> Content-Type: {content_type}")

        if "multipart/form-data" not in content_type:
            return Response(
                content='{"error": {"message": "Content-Type must be multipart/form-data"}}',
                status_code=415,
                media_type="application/json"
            )

        # =========================
        # 1️⃣ 解析 multipart（⚠️ 只讀一次）
        # =========================
        form = await request.form()

        model_name = form.get("model", "qwen3-asr-1.7b")
        language = form.get("language", "zh")
        response_format = form.get("response_format", "json")

        file_field = form.get("file") or form.get("audio")

        if not file_field:
            return Response(
                content='{"error": {"message": "No file provided"}}',
                status_code=400,
                media_type="application/json"
            )

        try:
            audio_bytes = await file_field.read()
            filename = getattr(file_field, "filename", "audio.wav")
            content_type_file = getattr(file_field, "content_type", "audio/wav")
        except Exception as e:
            return Response(
                content=_json.dumps({"error": {"message": str(e)}}),
                status_code=400,
                media_type="application/json"
            )

        # =========================
        # 2️⃣ Router（你原本的）
        # =========================
        info = get_model_info(route_table, model_name)
        provider = info.get("provider", "vllm")

        if provider == "vllm":
            target = info["base_url"] + "/v1/audio/transcriptions"
        else:
            target = info["url"]

        print(f">>> ASR 轉發到: {target}")

        # =========================
        # 3️⃣ 重新組 multipart（🔥 正確做法）
        # =========================
        files = {
            "file": (filename, audio_bytes, content_type_file)
        }

        data = {
            "model": model_name,
            "language": language,
            "response_format": response_format
        }

        # =========================
        # 4️⃣ 發送請求
        # =========================
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                target,
                files=files,
                data=data
            )

        # =========================
        # 5️⃣ 錯誤處理
        # =========================
        if resp.status_code != 200:
            print(">>> 上游錯誤:", resp.text)
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                media_type="application/json"
            )

        # =========================
        # 6️⃣ 回傳（OpenAI格式）
        # =========================
        if response_format == "text":
            return Response(
                content=resp.text,
                media_type="text/plain"
            )

        return Response(
            content=resp.content,
            status_code=200,
            media_type="application/json"
        )

    #4/28

    # async def asr_proxy(request: Request):
    #     key = extract_key(request)
    #     user = decode_api_key(key)
    #     print(f">>> ASR 請求來自: {user['student_id']}")

    #     content_type = request.headers.get("content-type", "")
    #     print(f">>> ASR Content-Type: {content_type}")

    #     # 解析請求，取出 model、audio bytes、audio format
    #     audio_bytes  = None
    #     audio_format = "wav"
    #     response_format = "json"

    #     if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
    #         form            = await request.form()
    #         model_name      = form.get("model", "qwen3-asr-1.7b")
    #         response_format = form.get("response_format", "json")
    #         file_field      = form.get("file") or form.get("audio")
    #         if file_field and isinstance(file_field, UploadFile):
    #             audio_bytes  = await file_field.read()
    #             fname        = file_field.filename or "audio.wav"
    #             audio_format = fname.rsplit(".", 1)[-1].lower() if "." in fname else "wav"
    #     else:
    #         body            = await request.json()
    #         model_name      = body.get("model", "qwen3-asr-1.7b")
    #         response_format = body.get("response_format", "json")
    #         # 若 JSON body 裡直接含 input_audio，取出 bytes
    #         try:
    #             audio_b64    = body["messages"][0]["content"][0]["input_audio"]["data"]
    #             audio_format = body["messages"][0]["content"][0]["input_audio"].get("format", "wav")
    #             audio_bytes  = base64.b64decode(audio_b64)
    #         except (KeyError, IndexError):
    #             audio_bytes = None

    #     info     = get_model_info(route_table, model_name)
    #     provider = info.get("provider", "vllm")

    #     async with httpx.AsyncClient(timeout=60) as client:
    #         if provider == "vllm" and audio_bytes is not None:
    #             # vLLM ASR 後端不支援原生 /v1/audio/transcriptions
    #             # 轉換成 /v1/chat/completions + input_audio (base64)
    #             target = info["base_url"] + "/v1/chat/completions"
    #             print(f">>> ASR vLLM 轉換為 chat/completions: {target}")
    #             payload = {
    #                 "model": model_name,
    #                 "messages": [
    #                     {
    #                         "role": "user",
    #                         "content": [
    #                             {
    #                                 "type": "input_audio",
    #                                 "input_audio": {
    #                                     "data":   base64.b64encode(audio_bytes).decode(),
    #                                     "format": audio_format,
    #                                 },
    #                             }
    #                         ],
    #                     }
    #                 ],
    #             }
    #             resp = await client.post(target, json=payload)

    #             if resp.status_code != 200:
    #                 return Response(content=resp.content, status_code=resp.status_code, media_type="application/json")

    #             # 把 chat/completions 回傳包裝成 OpenAI transcription 格式
    #             try:
    #                 text = resp.json()["choices"][0]["message"]["content"]
    #             except (KeyError, IndexError):
    #                 text = resp.text
    #             result = {"text": text}
    #             if response_format == "text":
    #                 return Response(content=text, media_type="text/plain")
    #             import json as _json
    #             return Response(content=_json.dumps(result, ensure_ascii=False), status_code=200, media_type="application/json")

    #         else:
    #             # 原生支援 /v1/audio/transcriptions 的後端（如 Whisper），直接轉發
    #             target = info["url"]
    #             print(f">>> ASR 直接轉發: {target}")
    #             if audio_bytes is not None:
    #                 resp = await client.post(
    #                     target,
    #                     files={"file": (f"audio.{audio_format}", audio_bytes, f"audio/{audio_format}")},
    #                     data={"model": model_name, "response_format": response_format},
    #                 )
    #             else:
    #                 resp = await client.post(target, content=await request.body(),
    #                                          headers={"content-type": content_type})

    #             if resp.status_code != 200:
    #                 return Response(content=resp.content, status_code=resp.status_code, media_type="application/json")
    #             if response_format == "text":
    #                 return Response(content=resp.content, media_type="text/plain")
    #             return Response(content=resp.content, status_code=200, media_type="application/json")

    # Fish Speech ASR — POST /v1/asr (multipart/form-data)
    # 欄位: audio (file), language (str|null), ignore_timestamps (bool, 預設 true)
    # 回傳: {"text": "...", "duration": ..., "segments": [...]}
    @app.post("/v1/asr")
    async def fish_asr_proxy(request: Request):
        key = extract_key(request)
        user = decode_api_key(key)
        print(f">>> Fish ASR 請求來自: {user['student_id']}")

        form = await request.form()
        model_name       = form.get("model", "fish-speech-server")
        language         = form.get("language", None)
        ignore_timestamps = form.get("ignore_timestamps", "true").lower() != "false"

        info   = get_model_info(route_table, model_name)
        target = info["base_url"] + "/v1/asr"
        print(f">>> Fish ASR 轉發目標: {target}")

        audio_field = form.get("audio")
        if audio_field is None:
            return Response(
                content='{"error": "缺少 audio 欄位"}',
                status_code=400,
                media_type="application/json",
            )

        audio_bytes   = await audio_field.read()
        filename      = audio_field.filename or "audio.wav"
        content_type  = audio_field.content_type or "audio/wav"

        files = {"audio": (filename, audio_bytes, content_type)}
        data  = {"ignore_timestamps": str(ignore_timestamps).lower()}
        if language:
            data["language"] = language

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(target, files=files, data=data)

        if resp.status_code != 200:
            print(f">>> Fish ASR 後端報錯: {resp.text}")
            return Response(content=resp.content, status_code=resp.status_code, media_type="application/json")

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
        response_format = body.get("response_format", "mp3")  # OpenAI 預設 mp3，pipecat 預設 pcm

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
