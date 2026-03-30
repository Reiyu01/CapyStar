import httpx
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

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