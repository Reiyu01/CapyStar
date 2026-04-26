# import hmac
# import hashlib
# import base64
# import time
# import os
# import re
# import yaml
# from fastapi import Request, HTTPException
# from dotenv import load_dotenv
# from litellm.proxy.proxy_server import UserAPIKeyAuth

# # 1. 讀取設定檔 (確保 config.yaml 裡有 role_permissions -> student)
# with open("config.yaml", "r") as f:
#     config = yaml.safe_load(f)
#     ROLE_PERMISSIONS = config.get("general_settings", {}).get("permissions_setting", {})



# load_dotenv()
# SECRET_KEY = os.getenv("SECRET_KEY")
# if not SECRET_KEY :
#     raise RuntimeError("SECRET_KEY 尚未設定")

# KEY_EXPIRE_DAYS = int(os.getenv("KEY_EXPIRE_DAYS"))
# if not KEY_EXPIRE_DAYS :
#     raise RuntimeError("金鑰期限 尚未設定")
# STUDENT_ID_PATTERN = re.compile(r"^[A-Z]\d{9}$")


# """
# 論步驟這邊是第二執行，第一為generate_api_key
# 產生雜湊字串，為了確保若掌握payload資料後每個人都能產生同樣的雜湊，因此用hmac能夠傳入，
# 能夠傳入伺服器自有金鑰混和進去
# """
# def _sign(payload: str) -> str:
#     """HMAC-SHA256簽名"""
#     return hmac.new(
#         SECRET_KEY.encode(),
#         payload.encode(),
#         hashlib.sha256
#     ).hexdigest()


# def generate_api_key(student_id: str) -> str:
#     """
#     產生API KEY
#     格式:base64(學號:時間戳記"HMAC簽名)
#     """

#     timestamp = str(int(time.time()))
#     payload = f"{student_id}:{timestamp}"
#     sig = _sign(payload)
#     raw = f"{payload}:{sig}"

#     #這邊用base64就不是再加密了，而是轉換成易於傳輸的格式
#     #urlsafe_b64encode 可確保轉換成key後放入網址能不會報錯能直接放入?api=
#     return base64.urlsafe_b64encode(raw.encode()).decode()

# async def decode_api_key(request: Request, auth_header: str):
#     """
#     LiteLLM 會傳入 request 物件與 auth_header (即 Authorization 欄位的值)
#     """
#     try:
#         # 1. 提取 Token
#         # auth_header 可能是 "Bearer <token>"，需要去的前綴
#         if auth_header.startswith("Bearer "):
#             token = auth_header.replace("Bearer ", "")
#         else:
#             token = auth_header

#         # 2. Base64 解碼 (現在 token 是字串了)
#         decoded = base64.urlsafe_b64decode(token.encode()).decode()

#         parts = decoded.split(":")
#         if len(parts) != 3:
#             raise ValueError("格式錯誤")
        
#         student_id, timestamp, sig = parts

#         # 3. HMAC 簽名驗證
#         expected = _sign(f"{student_id}:{timestamp}")
#         if not hmac.compare_digest(sig, expected):
#             raise ValueError("簽名不符")
        
#         # 4. 有效期限判定
#         if time.time() - int(timestamp) > KEY_EXPIRE_DAYS * 86400:
#             raise ValueError(f"Key 已過期")

#         # 5. 權限設定
#         perm = ROLE_PERMISSIONS.get("student")
#         if not perm:
#             raise ValueError("未設定職位權限")

#         # 回傳 LiteLLM 要求的字典格式
#         return {
#             "decision": True,          # 必須包含：允許通過
#             "user_id": student_id,
#             "rpm_limit": perm.get("rpm_limit"),
#             "tpm_limit": perm.get("tpm_limit"), # 修正原本程式碼中的拼錯 linit -> limit
#             "max_budget": perm.get("max_budget"),
#             "metadata": {"role": "student"}
#         }

#     except Exception as e:
#         print(f"驗證攔截：{str(e)}") 
#         # 直接拋出 HTTPException 讓 LiteLLM 捕獲
#         raise HTTPException(status_code=401, detail=f"API Key 驗證失敗: {str(e)}")

#     #TODO: 後續可回傳e 為log 這邊detail不直接回傳{e}是避免提供錯誤資訊給不正當使用者

# # TODO: 確認傳入的api在哪裡，目前寫兩者
# def extract_key(request:Request) -> str:
#     """從從 x-api-key header 或 Authorization: Bearer 取出 Key"""

#     key = request.headers.get("x-api-key", "")
#     if not key:
#         auth = request.headers.get("Authorization", "")
#         key = auth.removeprefix("Bearer ").strip()

#     if not key:
#         raise HTTPException(status_code=401, detail = "未讀取到API Key")
#     return key
















import hmac
import hashlib
import base64
import time
import os
import re
import yaml
from fastapi import Request, HTTPException
from dotenv import load_dotenv
from litellm.proxy.proxy_server import UserAPIKeyAuth

# 1. 讀取設定檔 (確保 config.yaml 裡有 role_permissions -> student)
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)
    ROLE_PERMISSIONS = config.get("general_settings", {}).get("role_permissions", {})


load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY :
    raise RuntimeError("SECRET_KEY 尚未設定")

KEY_EXPIRE_DAYS = int(os.getenv("KEY_EXPIRE_DAYS"))
if not KEY_EXPIRE_DAYS :
    raise RuntimeError("金鑰期限 尚未設定")
STUDENT_ID_PATTERN = re.compile(r"^[A-Z]\d{9}$")


"""
論步驟這邊是第二執行，第一為generate_api_key
產生雜湊字串，為了確保若掌握payload資料後每個人都能產生同樣的雜湊，因此用hmac能夠傳入，
能夠傳入伺服器自有金鑰混和進去
"""
def _sign(payload: str) -> str:
    """HMAC-SHA256簽名"""
    return hmac.new(
        SECRET_KEY.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()


def generate_api_key(student_id: str) -> str:
    """
    產生API KEY
    格式:base64(學號:時間戳記"HMAC簽名)
    """

    timestamp = str(int(time.time()))
    payload = f"{student_id}:{timestamp}"
    sig = _sign(payload)
    raw = f"{payload}:{sig}"

    #這邊用base64就不是再加密了，而是轉換成易於傳輸的格式
    #urlsafe_b64encode 可確保轉換成key後放入網址能不會報錯能直接放入?api=
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_api_key( key : str) -> dict:
    """
    驗證並解碼API Key
    這邊不直接讀DB，而是採用驗證格式簽名以及有效期限
    會回傳 {"student_id": xxx, "timestamp":}
    失敗拋出驗證失敗403

    共計驗證: 1.判斷是否有三個":" 2.判斷學號格式 3.將decode出來的學號日期再與伺服器金鑰給_sign函式加密 再與 其傳入的sig進行比對
    """
    try:
        decoded = base64.urlsafe_b64decode(key.encode()).decode()

        parts = decoded.split(":")
        if len(parts) !=3:
            raise ValueError("格式錯誤")
        
        #將parts的三個都賦予一個變數名稱
        student_id,timestamp,sig = parts

        """
        =======API KEY認證===========
        """
        #學號格式判斷
        if not STUDENT_ID_PATTERN.match(student_id):
            raise ValueError("學號格式錯誤")
        
        #HMAC 簽名判斷
        expected = _sign(f"{student_id}:{timestamp}")
        """
        不用== 的原因是因為防止計時攻擊，意思是不正當使用者可以藉由電腦機制即從第一個字元開始判斷若不符立刻回傳
        而不正當使用者可藉由判斷延遲時間得知到第幾個字元為正確的
        駭客可以逐位元地猜出正確的簽名，透過403延遲速度來逐步推敲出全部密碼
        而hmac.compare_digest()不管錯誤再哪個字元，回傳時間都是固定的
        就無法透過「時間差」來推敲出正確的簽名
        """
        if not hmac.compare_digest(sig, expected):
            raise ValueError("簽名不符")
        
        #有效期限判定
        if time.time() - int(timestamp) > KEY_EXPIRE_DAYS * 86400:
            raise ValueError(f"Key 已過期，請重新申請")

        return {"student_id":student_id, "timestamp": int(timestamp)}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=403, detail="API Key 格式錯誤或已失效")

    #TODO: 後續可回傳e 為log 這邊detail不直接回傳{e}是避免提供錯誤資訊給不正當使用者

# TODO: 確認傳入的api在哪裡，目前寫兩者
def extract_key(request:Request) -> str:
    """從從 x-api-key header 或 Authorization: Bearer 取出 Key"""

    key = request.headers.get("x-api-key", "")
    if not key:
        auth = request.headers.get("Authorization", "")
        key = auth.removeprefix("Bearer ").strip()

    if not key:
        raise HTTPException(status_code=401, detail = "未讀取到API Key")
    return key