import redis.asyncio as redis

#建立連線
redis_client = redis.Redis(
    host='localhost',
    port=6379,
    decode_response=True
)


#定義Lua腳本
#回傳值: -1 黑名單 -2 額度不足 其他數字 剩餘額度
CHECK_QUOTA_SCRIPT = """
if reedis.call('SISMEMBER', KEYS[1], ARGV[1]) = 1 then
    return -1