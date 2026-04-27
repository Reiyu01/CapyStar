# -*- coding: utf-8 -*-
"""
測試 Qwen3-ASR 兩種 HTTP 端點:
  1. POST /v1/chat/completions  (audio_url 或 base64 input_audio)
  2. POST /v1/audio/transcriptions  (OpenAI SDK multipart)
"""

import base64
import httpx
from openai import OpenAI

# ── 設定 ──────────────────────────────────────────────────────────────────────
GATEWAY_BASE = "https://b225.54ucl.com/capystar/v1"
API_KEY      = "QzExMzExODIxMjoxNzc0ODY3NDQ2OjQxMDI5MDIzYjU5MDBlYjMyMWUyYzY0MTM3Njc4OGVlOWQ1ZjQyZDFjNjE2MjFjN2FmNTUxNjczMTkzZDU0OTc="
MODEL_NAME   = "qwen3-asr-1.7b"

# 公開測試音檔 (Qwen 官方提供)
AUDIO_URL    = "https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen3-ASR-Repo/asr_en.wav"
# 也可以換成本地檔案路徑，設 None 則從網路下載
LOCAL_AUDIO  = None  # e.g. "test_voice_fixed.wav"

# ─────────────────────────────────────────────────────────────────────────────

def load_audio_bytes() -> bytes:
    if LOCAL_AUDIO:
        with open(LOCAL_AUDIO, "rb") as f:
            return f.read()
    print(f"  下載測試音檔: {AUDIO_URL}")
    resp = httpx.get(AUDIO_URL, timeout=30)
    resp.raise_for_status()
    return resp.content


def test_chat_completions_audio_url():
    """
    方式 A: /v1/chat/completions + audio_url
    直接傳 URL，後端自行下載音訊
    """
    print("\n=== [1] /v1/chat/completions (audio_url) ===")
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "audio_url",
                        "audio_url": {"url": AUDIO_URL},
                    }
                ],
            }
        ],
    }
    resp = httpx.post(
        f"{GATEWAY_BASE}/chat/completions",
        json=payload,
        headers={"Authorization": f"Bearer {API_KEY}"},
        timeout=60,
    )
    print(f"  HTTP {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"  RAW: {data}")
        if "choices" in data:
            text = data["choices"][0]["message"]["content"]
            print(f"  辨識結果: {text}")
        else:
            print(f"  ⚠ 回傳格式不含 choices，見 RAW")
    else:
        print(f"  錯誤: {resp.text}")


def test_chat_completions_base64():
    """
    方式 B: /v1/chat/completions + input_audio (base64)
    把音檔 base64 後直接嵌入 messages
    """
    print("\n=== [2] /v1/chat/completions (input_audio base64) ===")
    audio_bytes = load_audio_bytes()
    audio_b64   = base64.b64encode(audio_bytes).decode()

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data":   audio_b64,
                            "format": "wav",
                        },
                    }
                ],
            }
        ],
    }
    resp = httpx.post(
        f"{GATEWAY_BASE}/chat/completions",
        json=payload,
        headers={"Authorization": f"Bearer {API_KEY}"},
        timeout=60,
    )
    print(f"  HTTP {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"  RAW: {data}")
        if "choices" in data:
            text = data["choices"][0]["message"]["content"]
            print(f"  辨識結果: {text}")
        else:
            print(f"  ⚠ 回傳格式不含 choices，見 RAW")
    else:
        print(f"  錯誤: {resp.text}")


def test_audio_transcriptions_sdk():
    """
    方式 C: /v1/audio/transcriptions — OpenAI SDK (multipart/form-data)
    最標準的 Whisper 相容格式
    """
    print("\n=== [3] /v1/audio/transcriptions (OpenAI SDK) ===")
    audio_bytes = load_audio_bytes()

    client = OpenAI(
        base_url=GATEWAY_BASE,
        api_key=API_KEY,
    )
    # SDK 要求傳 tuple: (filename, bytes, content_type)
    transcription = client.audio.transcriptions.create(
        model=MODEL_NAME,
        file=("audio.wav", audio_bytes, "audio/wav"),
    )
    print(f"  辨識結果: {transcription.text}")


def test_audio_transcriptions_raw():
    """
    方式 D: /v1/audio/transcriptions — 原生 httpx multipart (不用 SDK)
    """
    print("\n=== [4] /v1/audio/transcriptions (raw multipart) ===")
    audio_bytes = load_audio_bytes()

    resp = httpx.post(
        f"{GATEWAY_BASE}/audio/transcriptions",
        headers={"Authorization": f"Bearer {API_KEY}"},
        files={"file": ("audio.wav", audio_bytes, "audio/wav")},
        data={"model": MODEL_NAME},
        timeout=60,
    )
    print(f"  HTTP {resp.status_code}")
    if resp.status_code == 200:
        print(f"  辨識結果: {resp.json().get('text')}")
    else:
        print(f"  錯誤: {resp.text}")


if __name__ == "__main__":
    test_chat_completions_audio_url()
    test_chat_completions_base64()
    test_audio_transcriptions_sdk()
    test_audio_transcriptions_raw()
