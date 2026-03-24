import httpx
from fastapi import FastAPI,Request
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
import os

app = FastAPI()

load_dotenv()
AI_SERVER_IP = os.getenv("AI_SERVER_IP")

@app.get("/")
async def main_page():
    return("你想找甚麼")


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    
    is_stream = body.get("stream", False)
    target = f"{AI_SERVER_IP}/v1/chat/completions"

    if is_stream:
        async def event_stream():
            # 將 client 放在產生器內部，確保串流期間連線不中斷
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream("POST", target, json=body) as resp:
                    async for chunk in resp.aiter_text():
                        yield chunk
        return StreamingResponse(event_stream(), media_type="text/event-stream")
    
    else:
        # 非串流模式，維持原樣即可
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(target, json=body)
            #  JSONResponse 或直接回傳 resp.json()
            return resp.json()


@app.get("/health")
async def health():
     return {"status": "ok", "upstream": VLLM_BASE}


@app.get("/v1/models")
async def get_models():
    return {
        "object": "list",
        "data": [
            {
                "id": "mistral-675b",
                "object": "model",
                "created": 1677610602,
                "owned_by": "vllm"
            }
        ]
    }