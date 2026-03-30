import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI

from db.database import init_db
from auth.routes import router as auth_router
from fastapi.middleware.cors import CORSMiddleware
from core.router import load_config,build_route_table,build_v1_models_list
from core.proxy import register_proxy_routes
load_dotenv()
AI_SERVER_IP = os.getenv("AI_SERVER_IP")

@asynccontextmanager
async def lifespan(app:FastAPI):
    await init_db()
    yield


app = FastAPI(title="AI Gateway",lifespan=lifespan)

app.include_router(auth_router)

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
route_table = build_route_table(config,AI_SERVER_IP)

print("=== AI Gateway 啟動 ===")
print("已載入路由表:")
for model, url in route_table.items():
    print(f"{model} -> {url} ")
print("========================")

register_proxy_routes(app, route_table, config)

@app.get("/")
async def main_page():
    return("歡迎使用AI Gateway\n若有任何問題請來信聯絡C112118111@nkust.edu.tw")




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