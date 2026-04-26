import yaml
from fastapi import HTTPException
import time

# 每種模型類型對應的 API 路徑後綴
TYPE_ENDPOINT: dict[str, str] = {
    "llm":       "/v1/chat/completions",
    "tts":       "/v1/tts",
    "asr":       "/v1/audio/transcriptions",
    "embedding": "/v1/embeddings",
}

#負責讀取config.yaml檔案
def load_config(path: str = "config.yaml") -> dict:
    try:
        with open(path, "r") as f:
            #yaml.safe_load : 將Yaml格式轉換為python資料結構的安全方式
            return yaml.safe_load(f)
    except FileNotFoundError:
        raise RuntimeError(f"找不到 config 檔: {path}")


def build_route_table(config: dict, base_url: str) -> dict:
    """
    回傳格式:
    {
        "gpt-oss-120b": {
            "type":     "llm",
            "base_url": "http://{IP}/gpt-oss-120b",
            "url":      "http://{IP}/gpt-oss-120b/v1/chat/completions"
        },
        "fish-speech-server": {
            "type":     "tts",
            "base_url": "http://{IP}/fish-speech-server",
            "url":      "http://{IP}/fish-speech-server/v1/tts"
        },
        ...
    }
    """
    table = {}
    for model in config["models"]:
        model_type = model.get("type", "llm")
        endpoint   = TYPE_ENDPOINT.get(model_type, "/v1/chat/completions")
        base       = f"{base_url}{model['path']}"
        table[model["name"]] = {
            "type":     model_type,
            "base_url": base,
            "url":      f"{base}{endpoint}",
        }
    return table


def get_model_info(route_table: dict, model_name: str) -> dict:
    """回傳該模型的完整資訊 dict，包含 type / base_url / url。"""
    if model_name not in route_table:
        raise HTTPException(
            status_code=404,
            detail=f"{model_name}模型未找到，請確認模型名稱"
        )
    return route_table[model_name]


def get_target(route_table: dict, model_name: str) -> str:
    """回傳該模型的完整 endpoint URL（向下相容用）。"""
    return get_model_info(route_table, model_name)["url"]
    

def build_v1_models_list(config:dict) -> list:
    """/v1/models呼叫用"""
    current_time = int(time.time())
    return [ 
        {
            "id": model["name"],
            "object": "model",
            "created" : current_time,
            "owned_by": "vllm"
        }
        for model in config["models"]
        #串列推導式
    ]
if __name__ == "__main__":

#def load_config
#直接呼叫測試是否能讀取config.yaml

    # config_print = load_config()
    # print(config_print)


#def build_route_table

    # {
    #     "gpt-oss-120b": "http://{AI_SERVER_IP}/gpt-oss-120b/v1/chat/completions"
    # }

    config_data = load_config()
    response = build_route_table(config_data,"http://123.123.123.11")
    print(response)