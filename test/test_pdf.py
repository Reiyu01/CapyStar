# test_pdf.py
import base64
import httpx
import fitz  # pymupdf

# PDF 每頁轉成圖片
doc = fitz.open("2.pdf")
content = []

for page in doc:
    pix = page.get_pixmap(dpi=150)
    img_bytes = pix.tobytes("jpeg")
    b64 = base64.b64encode(img_bytes).decode()
    content.append({
        "type": "image_url",
        "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
    })

content.append({
    "type": "text",
    "text": "裡面寫了什麼"
})

payload = {
    "model": "qwen2.5vl:72b",
    "messages": [{"role": "user", "content": content}]
}

resp = httpx.post(
    "https://b225.54ucl.com/capystar/v1/chat/completions",
    json=payload,
    timeout=300
)

print(resp.status_code)
result = resp.json()
if "choices" in result:
    print(result["choices"][0]["message"]["content"])
else:
    print(result)