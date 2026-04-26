import hmac, hashlib, base64, time, os, re, yaml
from litellm.proxy.proxy_server import UserAPIKeyAuth

# 1. 讀取設定檔 (確保 config.yaml 裡有 role_permissions -> student)
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)
    ROLE_PERMISSIONS = config.get("general_settings", {}).get("role_permissions", {})

SECRET_KEY = os.getenv("SECRET_KEY")
KEY_EXPIRE_DAYS = int(os.getenv("KEY_EXPIRE_DAYS", 30))
STUDENT_ID_PATTERN = re.compile(r"^[A-Z]\d{9}$")

def _sign(payload: str) -> str:
    """HMAC-SHA256 簽名"""
    return hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()

async def my_verify_func(token: str, curr_user_setup: UserAPIKeyAuth):
    try:
        # 2. 解碼你原本的金鑰格式 (學號:時間戳記:簽名)
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        parts = decoded.split(":")
        
        if len(parts) != 3:
            raise ValueError("格式錯誤")
        
        student_id, timestamp, sig = parts

        # 3. 驗證學號與簽名 (完全沿用你的邏輯)
        if not STUDENT_ID_PATTERN.match(student_id):
            raise ValueError("學號格式錯誤")
        
        expected = _sign(f"{student_id}:{timestamp}")
        if not hmac.compare_digest(sig, expected):
            raise ValueError("簽名不符")
        
        # 4. 驗證有效期
        if time.time() - int(timestamp) > KEY_EXPIRE_DAYS * 86400:
            raise ValueError("Key 已過期")

        # 5. 【目前統一設定為學生】
        # 直接抓取 config.yaml 裡的 student 權限
        perm = ROLE_PERMISSIONS.get("student")
        if not perm:
            raise ValueError("設定檔中找不到 'student' 的權限設定")

        # 6. 回傳給 LiteLLM 套用限制
        return {
            "user_id": student_id,
            "rpm_limit": perm.get("rpm_limit"),
            "tpm_limit": perm.get("tpm_limit"),
            "max_budget": perm.get("max_budget"),
            "metadata": {"role": "student"}
        }

    except Exception as e:
        # 發生任何錯誤都會回傳 401 Unauthorized
        raise Exception(f"驗證失敗: {str(e)}")





# import redis.asyncio as redis

# # 建立全域 Redis 連線
# redis_client = redis.Redis(
#     host='localhost', # 替換為你的 Redis 伺服器 IP
#     port=6379,
#     decode_responses=True 
# )

# # 定義 Lua 腳本
# # 回傳值: -1 (黑名單), -2 (額度不足), 其他數字 (剩餘額度)
# CHECK_QUOTA_SCRIPT = """
# if redis.call('SISMEMBER', KEYS[1], ARGV[1]) == 1 then
#     return -1
# end
# local q = redis.call('GET', KEYS[2])
# if not q or tonumber(q) <= 0 then
#     return -2
# end
# return tonumber(q)
# """