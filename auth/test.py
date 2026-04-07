import redis.asyncio as redis

# 建立全域 Redis 連線
redis_client = redis.Redis(
    host='localhost', # 替換為你的 Redis 伺服器 IP
    port=6379,
    decode_responses=True 
)

# 定義 Lua 腳本
# 回傳值: -1 (黑名單), -2 (額度不足), 其他數字 (剩餘額度)
CHECK_QUOTA_SCRIPT = """
if redis.call('SISMEMBER', KEYS[1], ARGV[1]) == 1 then
    return -1
end
local q = redis.call('GET', KEYS[2])
if not q or tonumber(q) <= 0 then
    return -2
end
return tonumber(q)
"""