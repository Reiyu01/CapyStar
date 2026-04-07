# -*- coding: utf-8 -*-
import asyncio
import json
import librosa
import numpy as np
import pybase64 as base64
import websockets

# 請確保此 URL 與你 Log 中運作正常的格式一致
GATEWAY_URL = "wss://b225.54ucl.com/capystar/v1/realtime/qwen3-asr-1.7b"
API_KEY = "QzExMzExODIxMjoxNzc0ODY3NDQ2OjQxMDI5MDIzYjU5MDBlYjMyMWUyYzY0MTM3Njc4OGVlOWQ1ZjQyZDFjNjE2MjFjN2FmNTUxNjczMTkzZDU0OTc="
AUDIO_PATH = "test_voice_fixed.wav" 
MODEL_NAME = "qwen3-asr-1.7b"

async def debug_transcribe():
    uri = f"{GATEWAY_URL}?api_key={API_KEY}"
    print(f"🚀 連線中...")

    try:
        async with websockets.connect(uri) as ws:
            # 接收初始訊息
            await ws.recv() 

            # 1. 更新 Session
            await ws.send(json.dumps({"type": "session.update", "model": MODEL_NAME}))
            
            # 2. 轉換與傳送音訊
            audio, _ = librosa.load(AUDIO_PATH, sr=16000, mono=True)
            pcm16 = (audio * 32767).astype(np.int16)
            audio_bytes = pcm16.tobytes()
            
            chunk_size = 4096
            for i in range(0, len(audio_bytes), chunk_size):
                chunk = audio_bytes[i : i + chunk_size]
                await ws.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": base64.b64encode(chunk).decode("utf-8"),
                }))
            
            # 3. 觸發辨識
            print("⏳ 音訊上傳完成，等待辨識結果...")
            await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
            await ws.send(json.dumps({
                "type": "response.create",
                "response": {
                    "modalities": ["text"]
                }
            }))

            # 4. 接收數據流並在內部去重
            full_text_chunks = []
            exclude_tokens = ["<asr_text>", "language", " English", "", None]
            
            while True:
                try:
                    raw_message = await ws.recv()
                    data = json.loads(raw_message)
                    
                    # 處理文字片段
                    if "delta" in data:
                        text_chunk = data["delta"]
                        if text_chunk not in exclude_tokens:
                            # 去重邏輯：如果當前碎片與上一個相同則跳過 (處理 ASR 重複發送)
                            if not full_text_chunks or full_text_chunks[-1] != text_chunk:
                                full_text_chunks.append(text_chunk)
                    
                    # 判定結束訊號
                    if data.get("type") in ["response.done", "transcription.done", "error"]:
                        if data.get("type") == "error":
                            print(f"❌ 伺服器錯誤: {data.get('error')}")
                        break
                        
                except websockets.exceptions.ConnectionClosed:
                    break

            # 5. 一次性整理並輸出
            # 去掉可能的重複字串拼湊 (如: "你好你好" -> "你好")
            final_result = "".join(full_text_chunks).strip()
            
            # 輸出最終結果
            print(f"\n✨ 辨識結果：{final_result}")
            print("✅ 任務完成")

    except Exception as e:
        print(f"❌ 程式發生異常: {e}")

if __name__ == "__main__":
    asyncio.run(debug_transcribe())