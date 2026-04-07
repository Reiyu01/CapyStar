# -*- coding: utf-8 -*-
import asyncio
import json
import librosa
import numpy as np
import pybase64 as base64
import websockets

GATEWAY_URL = "wss://b225.54ucl.com/capystar/v1/realtime/qwen3-asr-1.7b"
API_KEY = "QzExMzExODIxMjoxNzc0ODY3NDQ2OjQxMDI5MDIzYjU5MDBlYjMyMWUyYzY0MTM3Njc4OGVlOWQ1ZjQyZDFjNjE2MjFjN2FmNTUxNjczMTkzZDU0OTc="
AUDIO_PATH = "test_voice_fixed.wav" 
MODEL_NAME = "qwen3-asr-1.7b"

async def debug_transcribe():
    uri = f"{GATEWAY_URL}?api_key={API_KEY}"
    print(f"🚀 連線中: {uri}")

    async with websockets.connect(uri) as ws:
        # 1. 接收連線訊息
        print(f"RAW RECV: {await ws.recv()}")

        # 2. 更新 Session
        await ws.send(json.dumps({"type": "session.update", "model": MODEL_NAME}))
        
        # # 3. 官方 ASR 啟動流程
        # await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))

        # 4. 轉換與傳送音訊 (Chunking)
        audio, _ = librosa.load(AUDIO_PATH, sr=16000, mono=True)
        pcm16 = (audio * 32767).astype(np.int16)
        audio_bytes = pcm16.tobytes()
        
        total_chunks = len(audio_bytes) // 4096 + 1
        print(f"📤 傳送音訊中... (總計 {total_chunks} 個封包)")
        
        chunk_size = 4096
        for idx, i in enumerate(range(0, len(audio_bytes), chunk_size)):
            chunk = audio_bytes[i : i + chunk_size]
            await ws.send(json.dumps({
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(chunk).decode("utf-8"),
            }))
            
            # 每傳送 10 個封包印一次進度，避免畫面太亂
            if (idx + 1) % 10 == 0:
                print(f"   已傳送 {idx + 1} / {total_chunks} 封包...")
                
            # 改成 0.01 秒，或者甚至拿掉，讓它以最快速度傳完
            await asyncio.sleep(0.01) 

        # 5. 強制觸發辨識
        print("⏳ 音訊傳送完畢，觸發辨識 (commit & create)...")
        # await ws.send(json.dumps({"type": "input_audio_buffer.commit", "final": True}))
        await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
        
        # 步驟 5-2: 請求產生回應 (這就是按下 Enter 鍵！)
        await ws.send(json.dumps({
            "type": "response.create",
            "response": {
                "modalities": ["text"]  # 告訴模型我們只要文字輸出
            }
        }))

        # 6. 【關鍵】接收並重組數據流
            # 6. 接收並重組數據流
        print("\n📡 辨識結果：", end="", flush=True)
        full_transcript = ""
        
        while True:
            try:
                raw_message = await ws.recv()
                data = json.loads(raw_message)
                
                if "delta" in data:
                    text_chunk = data["delta"]
                    # 過濾掉控制字元
                    if text_chunk not in ["<asr_text>", "language", " English", ""]:
                        full_transcript += text_chunk
                        print(f"\r即時字幕: {full_transcript}", end="", flush=True)
                        
                if data.get("type") == "transcription.done" or data.get("type") == "response.done":
                    print("\n\n✅ 辨識完成！")
                    
                    # --- 新增：儲存至文字檔 ---
                    output_filename = "transcript_result.txt"
                    with open(output_filename, "w", encoding="utf-8") as f:
                        f.write(full_transcript)
                    print(f"💾 結果已儲存至: {output_filename}")
                    # -----------------------
                    
                    break
                    
            except Exception as e:
                print(f"\n連線中斷: {e}")
                break
        # print("\n📡 辨識結果：", end="", flush=True)
        # full_transcript = ""
        
        # while True:
        #     try:
        #         raw_message = await ws.recv()
        #         data = json.loads(raw_message)
                
        #         if "delta" in data:
        #             text_chunk = data["delta"]
        #             # 過濾掉 Qwen3 專屬的控制字元
        #             if text_chunk not in ["<asr_text>", "language", " English", ""]:
        #                 full_transcript += text_chunk
        #                 # 使用 \r 讓文字在同一行不斷更新（覆蓋）
        #                 print(f"\r即時字幕: {full_transcript}", end="", flush=True)
                        
        #         if data.get("type") == "transcription.done" or data.get("type") == "response.done":
        #             print("\n\n✅ 辨識完成！")
        #             break
                    
        #     except Exception as e:
        #         print(f"\n連線中斷: {e}")
        #         break






        # print("📡 接收原始數據流:")
        # while True:
        #     try:
        #         # 這裡不加任何 if 判斷，直接印出伺服器給的所有東西
        #         raw_message = await ws.recv()
        #         print(f"\n[SERVER DATA]: {raw_message}")
                
        #         # 簡單解析看有沒有文字
        #         data = json.loads(raw_message)
        #         if "delta" in data:
        #             print(f">>> 發現文字: {data['delta']}")
        #         if data.get("type") == "transcription.done":
        #             break
        #     except Exception as e:
        #         print(f"連線中斷: {e}")
        #         break

if __name__ == "__main__":
    asyncio.run(debug_transcribe())
