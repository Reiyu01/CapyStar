import asyncio
import websockets
import aiofiles
import json
import time
from dotenv import load_dotenv
import os
load_dotenv = os.getenv("test_key")
# === 設定區 ===
GATEWAY_URL = ""
API_KEY = ""
AUDIO_FILE = "test_voice.wav"  # 你的音檔路徑
CHUNK_SIZE = 4000  # 每次傳送的大小 (約 125ms 的音訊)

async def send_audio(websocket):
    """模擬麥克風，持續讀取檔案並發送"""
    print(" [📤] 開始傳送音訊流...")
    async with aiofiles.open(AUDIO_FILE, mode='rb') as f:
        while True:
            chunk = await f.read(CHUNK_SIZE)
            if not chunk:
                # 傳送結束信號 (視你的模型協議而定，有些是傳文字 {"type": "end"})
                # await websocket.send(json.dumps({"event": "stop"})) 
                break
            
            await websocket.send(chunk)
            # 模擬真實說話速度，不要一次全部塞進去
            await asyncio.sleep(0.1) 
    print(" [📤] 檔案傳送完畢。")

async def receive_text(websocket):
    """持續接收 A 機房回傳的辨識結果"""
    print(" [📥] 等待辨識結果...")
    try:
        async for message in websocket:
            # 假設後端回傳的是 JSON 字串
            print(f" [✨ 辨識中]: {message}")
    except websockets.exceptions.ConnectionClosed:
        print(" [📥] 連線已由伺服器關閉。")

async def main():
    # 將 API Key 帶在 Query String 中
    uri = f"{GATEWAY_URL}?api_key={API_KEY}"
    
    try:
        async with websockets.connect(uri) as websocket:
            print(f" ✅ 已連接至 Gateway: {GATEWAY_URL}")
            
            # 同時執行發送與接收
            await asyncio.gather(
                send_audio(websocket),
                receive_text(websocket)
            )
    except Exception as e:
        print(f" ❌ 錯誤: {e}")

if __name__ == "__main__":
    asyncio.run(main())