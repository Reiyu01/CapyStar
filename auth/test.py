import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI

from db.database import init_db
from auth.routes import router as auth_router
from core.router import load_config, build_route_table, build_v1_models_list
from core.proxy import register_proxy_routes

load_dotenv()
AI_SERVER_IP = os.getenv("AI_SERVER_IP")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Capy-Star Gateway", lifespan=lifespan)

# 掛載認證路由
app.include_router(auth_router)

# 載入模型路由表
config      = load_config("config.yaml")
route_table = build_route_table(config, AI_SERVER_IP)

print("=== Capy-Star Gateway 啟動 ===")
print(f"Upstream: {AI_SERVER_IP}")
print("已載入路由表:")
for model, url in route_table.items():
    print(f"  {model} -> {url}")
print("==============================")

# 掛載代理路由
register_proxy_routes(app, route_table, config)


@app.get("/")
async def main_page():
    return {
        "message": "歡迎使用 Capy-Star AI Gateway",
        "models": list(route_table.keys())
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "upstream": AI_SERVER_IP,
        "models": list(route_table.keys())
    }


@app.get("/v1/models")
async def get_models():
    return {
        "object": "list",
        "data": build_v1_models_list(config)
    }