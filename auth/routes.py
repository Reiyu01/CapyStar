import time
import aiosqlite
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from auth.keygen import generate_api_key, decode_api_key, extract_key
from db.database import DB_PATH

#TODO: 該錯誤處理應該放置於routes還是keygen
load_dotenv()
KEY_EXPIRE_DAYS = int(os.getenv("KEY_EXPIRE_DAYS"))
if not KEY_EXPIRE_DAYS :
    raise RuntimeError("金鑰期限 尚未設定")

router = APIRouter(prefix="/auth", tags=["auth"])

class GenerateRequest(BaseModel):
    student_id: str


#------1. Token 生成 -----------
#用post可以將請求放入body中確保資料不會直接顯示在網址上，而get會顯示網址上，因此更安全。
#且post能夠根據body的輸入生成新資料
@router.post("/generate-key")
async def token_generator(body: GenerateRequest)
    """
    產生 API Key 並存入DB
    呼叫方: 學校 Oauth完成後的前端
    """
    #TODO: 這邊輸入資料為student_id，要與前端人員討論一下輸入格式
    student_id = body.student_id.strip().upper()
    if not student_id:
        raise HTTPException(status_code=400, detail= "未讀取到Student id")
    
    api_key = generate_api_key(student_id)
    created_at = int(time.time())


    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO api_keys (student_id, api_key, created_at) VALUES (?,?,?)",
            (student_id, api_key, created_at)
        )
        await db.commit()

    return {
        "student_id": student_id,
        "api_key": api_key,
        "created_at": created_at,
        "expires_at": created_at + (KEY_EXPIRE_DAYS * 86400),
        "expires_in": f"{KEY_EXPIRE_DAYS} days"
    }

#------2. Token 檢查 -----------
#TODO: 或許可以更名為/keys/verify更為符合RESTFul
@router.post("/check-key")
async def token_check(request: Request):
    """
    驗證 API KEY 是否合法
    由解碼驗證格式與簽名
    """
    key =  extract_key(request)
    info = decode_api_key(key)
    #TODO: "expires_in": f"{KEY_EXPIRE_DAYS} days"
    return {
        "valid":      True,
        "student_id": info["student_id"],
        "issued_at":  info["timestamp"],
        "expires_at": info["timestamp"] + (KEY_EXPIRE_DAYS * 86400)
    }

#TODO: 可以改成GET /students/{student_id}/keys更符合RESTful
#------3. Token 列表回傳 -----------
@router.get("/students/{student_id}")
async def token_account(student_id: str, request: Request):
    """
    回傳該學號的所有金鑰
    須帶著本人有效的 API KEY 才能查詢
    """

    key = extract_key(request)
    info = decode_api_key(key)

    if info["student_id"].upper() != student_id.upper():
        raise HTTPException(status_code=403, detail="查詢身分不符")

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT api_key,created_at,is_active
            FROM api_keys
            WHERE student_id = ?
            ORDER BY created_at DESC
            """,
            (student_id.upper(),)
        )
        rows = await cursor.fetchall()

    return {
        "student_id": student_id.upper(),
        "total":      len(rows),
        "keys": [
            {
                "api_key":    row["api_key"],
                "created_at": row["created_at"],
                "expires_at": row["created_at"]  + (KEY_EXPIRE_DAYS * 86400),
                "is_active":  bool(row["is_active"])
            }
            for row in rows
        ]
    }