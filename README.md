sudo nano /etc/systemd/system/capy-star.service





# Capy-Star (API Proxy)

這是一個 FastAPI Proxy 服務，主要用來轉發 OpenAI-Compatible 的 API 請求。

## API Call Example

這裡示範如何呼叫聊天補全 (Chat Completions) API。

### 1. 使用 cURL (Command Line)

Windows CMD 或 Linux Terminal 皆適用：

```bash
curl http://163.18.26.230:8000/v1/chat/completions \
 -H "Content-Type: application/json" \
 -d '{"model":"mistral-675b","messages":[{"role":"user","content":"你好"}]}'
```

*(註：Windows CMD 使用者請將單引號換成雙引號，並注意跳脫規則)*

### 成功回應範例 (Response)

```json
{
  "id": "chatcmpl-9c5ed9f877464424",
  "object": "chat.completion",
  "created": 1773948440,
  "model": "mistral-675b",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "你好！😊 有什么可以帮助你的吗？比如解答问题、聊天、提供建議等等～",
        "tool_calls": []
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 4,
    "total_tokens": 34,
    "completion_tokens": 30
  }
}
```

---

### 2. 使用 Python (requests)

如果你想用 Python 程式測試：

```python
import requests

url = "http://163.18.26.230:8000/v1/chat/completions"

payload = {
    "model": "mistral-675b",
    "messages": [
        {"role": "user", "content": "你好"}
    ],
    "stream": False
}

headers = {"Content-Type": "application/json"}

try:
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status() # 檢查是否有錯誤 (非 200)
    print(response.json())
except Exception as e:
    print(f"Error: {e}")
```

---

### 3. Server-Sent Events (SSE) / Streaming 串流模式

若要使用即時串流 (Streaming) 回應，請將 `stream` 參數設為 `True`。

**使用 cURL:**

```bash
# 加上 -N (no-buffer) 確保即時看到輸出
curl -N http://163.18.26.230:8000/v1/chat/completions \
 -H "Content-Type: application/json" \
 -d '{"model":"mistral-675b","messages":[{"role":"user","content":"你好"}], "stream": true}'
```

**使用 Python:**

```python
import requests
import json

url = "http://163.18.26.230:8000/v1/chat/completions"

payload = {
    "model": "mistral-675b",
    "messages": [
        {"role": "user", "content": "你好"}
    ],
    "stream": True # 啟用 Streaming
}

headers = {"Content-Type": "application/json"}

try:
    with requests.post(url, json=payload, headers=headers, stream=True) as response:
        response.raise_for_status()
        
        print("開始接收串流回應 (Streaming)...")
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                # SSE 格式回傳會以 "data: " 開頭
                if decoded_line.startswith("data: "):
                    content = decoded_line[6:] # 移除 "data: " 前綴
                    if content == "[DONE]":
                        print("\n[串流結束]")
                        break
                    
                    try:
                        data = json.loads(content)
                        # 從 delta 取出新生成的文字片段
                        delta = data["choices"][0].get("delta", {}).get("content", "")
                        print(delta, end="", flush=True)
                    except json.JSONDecodeError:
                        continue
except Exception as e:
    print(f"Error: {e}")
```
