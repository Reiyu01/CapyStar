import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI

from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from core.router import load_config,build_route_table,get_target,build_v1_models_list

load_dotenv()
AI_SERVER_IP = os.getenv("AI_SERVER_IP")

app = FastAPI(title="AI Gateway",lifespan=lifespan)


# --- 新增 CORS 設定 ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允許所有來源，開發環境建議用 *
    allow_credentials=True,
    allow_methods=["*"],  # 必須包含 OPTIONS，* 代表全部允許
    allow_headers=["*"],
)
# ----------------------





#建構可讀取python格式
config = load_config("config.yaml")
#建構列表(模型與對應網址)
available_model_table = build_route_table(config,AI_SERVER_IP)

print("=== AI Gateway 啟動 ===")
print("已載入路由表:")
for model, url in available_model_table.items():
    print(f"{model} -> {url} ")
print("========================")

@app.get("/")
async def main_page():
    return("歡迎使用AI Gateway\n若有任何問題請來信聯絡C112118111@nkust.edu.tw")


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    
    is_stream = body.get("stream", False)
    
    #不可路由
    #target = f"{AI_SERVER_IP}/v1/chat/completions"

    target = get_target(available_model_table,body.get("model",""))

    if is_stream:
        async def event_stream():
            # 將 client 放在產生器內部，確保串流期間連線不中斷
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream("POST", target, json=body) as resp:
                    async for chunk in resp.aiter_text():
                        yield chunk
        return StreamingResponse(event_stream(), media_type="text/event-stream")
    
    else:
        # 非串流模式
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(target, json=body)
            #  JSONResponse 或直接回傳 resp.json()
            return resp.json()


@app.get("/health")
async def health():
     return {"status": "ok", "upstream": VLLM_BASE}
'''
未加入呼叫健康檢查
'''

@app.get("/v1/models")
async def get_models():
    return {
        "object": "list",
        "data": build_v1_models_list(config)
    }