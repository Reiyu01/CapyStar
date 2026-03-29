# test_image.py
import base64
import httpx

with open("2.pdf", "rb") as f:
    b64 = base64.b64encode(f.read()).decode()

payload = {
    "model": "qwen2.5vl:72b",
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:application/pdf;base64,{b64}"
                        #f"data:application/pdf;base64,{b64}
                        #f"data:image/jpeg;base64,{b64}"
                    }
                },
                {
                    "type": "text",
                    "text": "裡面寫了甚麼"
                }
            ]
        }
    ]
}

resp = httpx.post(
    "https://b225.54ucl.com/capystar/v1/chat/completions",
    json=payload,
    timeout=120
)


print(resp.status_code)
print(resp.json())
print(resp.json()["choices"][0]["message"]["content"])
