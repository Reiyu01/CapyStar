import requests
import base64

# 1. 將你的自定義語音檔轉成 Base64 字串
def get_audio_base64(file_path):
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8')
# 你的代理伺服器網址
url = "https://b225.54ucl.com/capystar/v1/tts" 

headers = {
    # 確保這個 Bearer Token 是有效的
    "Authorization": "Bearer QzExMzExODIxMjoxNzc0ODY3NDQ2OjQxMDI5MDIzYjU5MDBlYjMyMWUyYzY0MTM3Njc4OGVlOWQ1ZjQyZDFjNjE2MjFjN2FmNTUxNjczMTkzZDU0OTc=",
    "Content-Type": "application/json"
}

data = {
    "model": "fish-speech-server",
    "text": "你好今天天氣真好",
    "format": "mp3",
    "normalize": True,
    "latency": "normal"
}


# # 這是發給代理伺服器的資料 (OpenAI 格式)
# data = {
#     "model": "fish-speech-server",
#     "input": "[angry]你好，這是一段測試語音。",  # 代理層要轉成 "text"
#     "voice": "alex",                  # 代理層要轉成 "reference_id" (若有需要)
#     "response_format": "mp3",         # 代理層要轉成 "format"
#     "speed": 1.0
# }

print(f"正在發送請求至: {url}...")

try:
    response = requests.post(url, headers=headers, json=data, timeout=60)
    
    if response.status_code == 200:
        with open("output.mp3", "wb") as f:
            f.write(response.content)
        print("✅ 語音合成成功！已儲存為 output.mp3")
    else:
        print(f"❌ 合成失敗，狀態碼: {response.status_code}")
        print(f"錯誤訊息: {response.text}")

except Exception as e:
    print(f"💥 發生錯誤: {e}")


# import requests

# url = "https://b225.54ucl.com/capystar/v1/tts" 
# headers = {
#     "Authorization": "Bearer QzExMzExODIxMjoxNzc0ODY3NDQ2OjQxMDI5MDIzYjU5MDBlYjMyMWUyYzY0MTM3Njc4OGVlOWQ1ZjQyZDFjNjE2MjFjN2FmNTUxNjczMTkzZDU0OTc=",
#     "Content-Type": "application/json"
# }

# data = {
#     "model": "fish-speech-server",  # 模型名稱
#     "input": "你好，這是一段測試語音。", # 要轉的文字
#     "voice": "alex",             # 角色名稱或 ID
#     "response_format": "mp3",    # 輸出格式
#     "speed": 1.0                 # 語速
# }

# response = requests.post(url, headers=headers, json=data)

# if response.status_code == 200:
#     with open("output.mp3", "wb") as f:
#         f.write(response.content)
#     print("語音合成成功！")
