import requests

# 請確保 PORT 與您 FastAPI 啟動的 PORT 一致
BASE_URL = "http://127.0.0.1:8000"

def run_tests():
    print("=== 開始測試 API 端點 ===")
    
    # 測試項目清單 (路由, 描述)
    endpoints = [
        ("/", "1. 主頁面 (Root)"),
        ("/health", "2. 健康檢查 (Health)"),
        ("/v1/models", "3. 獲取模型列表 (v1/models)")
    ]

    for path, description in endpoints:
        print(f"\n[測試] {description} -> GET {path}")
        try:
            response = requests.get(f"{BASE_URL}{path}", timeout=5)
            if response.status_code == 200:
                print(f"✅ 成功! 狀態碼: {response.status_code}")
                # 簡短印出回傳內容
                data = response.json()
                print(f"📄 回傳內容: {str(data)[:200]}...") 
            else:
                print(f"❌ 錯誤! 狀態碼: {response.status_code}")
                print(f"📄 錯誤訊息: {response.text}")
        except requests.exceptions.ConnectionError:
            print("⚠️ 連線失敗！請確認您的 FastAPI 伺服器是否已經啟動。")
        except Exception as e:
            print(f"⚠️ 發生未知的錯誤: {e}")

if __name__ == "__main__":
    run_tests()