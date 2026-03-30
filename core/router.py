import yaml
from fastapi import HTTPException
import time

#負責讀取config.yaml檔案
def load_config(path: str = "config.yaml") -> dict:
    try:

        with open(path,"r") as f:
            #yaml.safe_load : 將Yaml格式轉換為python資料結構的安全方式
            return yaml.safe_load(f)
    
    except FileNotFoundError:
        raise RuntimeError(f"找不到 config 檔: {path}")  # 改成 RuntimeError


def build_route_table(config: dict, base_url: str) -> dict:
    """
    範例回傳格式:
    {
        "gpt-oss-120b": "http://{AI_SERVER_IP}/gpt-oss-120b/v1/chat/completions"
    }
    """

    table = {}
    
    for model in config["models"]:
        table[model["name"]] = f"{base_url}{model['path']}/v1/chat/completions"
    return table


def get_target(available_model_table: dict, model_name: str) -> str:
    if model_name not in available_model_table:
        raise HTTPException(
            status_code=404,
            detail=f"{model_name}模型未找到，請確認模型名稱"
        )
    return available_model_table[model_name]
    

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