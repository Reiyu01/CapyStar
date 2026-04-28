# -*- coding: utf-8 -*-
"""
/v1/realtime 端點測試腳本（OpenAI Realtime Transcription 格式）

流程：
  連線 → session.created
       → session.update (設定語言)
       → input_audio_buffer.append × N (24kHz PCM16 base64)
       → input_audio_buffer.commit
       → 接收 input_audio_buffer.committed
       → 接收 conversation.item.input_audio_transcription.delta
       → 接收 conversation.item.input_audio_transcription.completed  ← 最終結果
"""
import asyncio
import json
import librosa
import numpy as np
import pybase64 as base64
import websockets

GATEWAY_URL = "wss://b225.54ucl.com/capystar/v1/realtime"
API_KEY     = "QzExMzExODIxMjoxNzc0ODY3NDQ2OjQxMDI5MDIzYjU5MDBlYjMyMWUyYzY0MTM3Njc4OGVlOWQ1ZjQyZDFjNjE2MjFjN2FmNTUxNjczMTkzZDU0OTc="
AUDIO_PATH  = "test_voice_fixed.wav"
MODEL_NAME  = "qwen3-asr-1.7b"
LANGUAGE    = "zh"
SAMPLE_RATE = 24000   # 端點固定 24kHz PCM16

async def debug_transcribe():
    uri = f"{GATEWAY_URL}?model={MODEL_NAME}&api_key={API_KEY}"
    print(f"🚀 連線中: {uri}")

    async with websockets.connect(uri) as ws:

        # 1. 接收 session.created
        raw = await ws.recv()
        data = json.loads(raw)
        print(f"✅ session.created: id={data.get('session', {}).get('id')}")

        # 2. session.update — 設定語言
        await ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "audio": {
                    "input": {
                        "transcription": {
                            "model": MODEL_NAME,
                            "language": LANGUAGE
                        }
                    }
                }
            }
        }))
        raw = await ws.recv()
        print(f"✅ session.updated")

        # 3. 載入音訊，重採樣到 24kHz，轉 PCM16
        audio, _ = librosa.load(AUDIO_PATH, sr=SAMPLE_RATE, mono=True)
        pcm16      = (audio * 32767).astype(np.int16)
        audio_bytes = pcm16.tobytes()

        chunk_size   = 4096
        total_chunks = (len(audio_bytes) + chunk_size - 1) // chunk_size
        print(f"📤 傳送音訊中... ({total_chunks} 個封包，共 {len(audio_bytes)} bytes)")

        for idx, i in enumerate(range(0, len(audio_bytes), chunk_size)):
            chunk = audio_bytes[i : i + chunk_size]
            await ws.send(json.dumps({
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(chunk).decode("utf-8"),
            }))
            if (idx + 1) % 20 == 0:
                print(f"   已傳送 {idx + 1} / {total_chunks} 封包...")

        # 4. commit — 觸發辨識
        print("⏳ 音訊傳送完畢，送出 commit...")
        await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))

        # 5. 接收所有事件，直到 completed
        full_transcript = ""
        print("\n📡 等待辨識結果...")

        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=30)
            except asyncio.TimeoutError:
                print("\n⚠️  等待逾時（30s），結束接收")
                break

            data = json.loads(raw)
            etype = data.get("type", "")

            if etype == "input_audio_buffer.committed":
                print(f"   [committed] item_id={data.get('item_id')}")

            elif etype == "conversation.item.input_audio_transcription.delta":
                delta = data.get("delta", "")
                full_transcript += delta
                print(f"\r   [delta] {full_transcript}", end="", flush=True)

            elif etype == "conversation.item.input_audio_transcription.completed":
                full_transcript = data.get("transcript", full_transcript)
                print(f"\n✅ 辨識完成: {full_transcript}")
                break

            elif etype == "error":
                print(f"\n❌ 錯誤: {data.get('error')}")
                break

            else:
                print(f"   [其他事件] {etype}")

        # 6. 儲存結果
        if full_transcript:
            output_file = "transcript_result.txt"
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(full_transcript)
            print(f"💾 結果已儲存至: {output_file}")






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
