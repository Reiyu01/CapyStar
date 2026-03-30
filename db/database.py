import os
import aiosqlite
from dotenv import load_dotenv

load_dotenv()
DB_PATH = os.getenv("DB_PATH")


async def init_db():
    """啟動時建立資料表（若不存在）"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id  TEXT    NOT NULL,
                api_key     TEXT    NOT NULL UNIQUE,
                created_at  INTEGER NOT NULL,
                is_active   INTEGER NOT NULL DEFAULT 1
            )
        """)
        await db.commit()
    print(f"DB 初始化完成：{DB_PATH}")

