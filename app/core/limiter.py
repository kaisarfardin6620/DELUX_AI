import time
import uuid
from redis.asyncio import Redis
from app.core import config

redis_client = Redis.from_url(config.REDIS_URL, decode_responses=True)

class ConnectionLimiter:
    async def acquire(self, user_id: int) -> bool:
        key = f"ws_conn:{user_id}"
        count = await redis_client.incr(key)
        
        if count == 1:
            await redis_client.expire(key, 86400)
            
        if count > config.WS_MAX_CONNECTIONS_PER_USER:
            await redis_client.decr(key)
            return False
        return True

    async def release(self, user_id: int) -> None:
        key = f"ws_conn:{user_id}"
        count = await redis_client.decr(key)
        if count <= 0:
            await redis_client.delete(key)

class MessageRateLimiter:
    def __init__(self, max_messages: int = 30, window_seconds: int = 60):
        self.max_messages = max_messages
        self.window_seconds = window_seconds

    async def is_allowed(self, user_id: int) -> bool:
        key = f"ws_rate:{user_id}"
        now = time.time()
        window_start = now - self.window_seconds
        event_id = uuid.uuid4().hex

        lua_script = """
        local key = KEYS[1]
        local now = tonumber(ARGV[1])
        local window_start = tonumber(ARGV[2])
        local max_messages = tonumber(ARGV[3])
        local event_id = ARGV[4]
        local window_seconds = tonumber(ARGV[5])

        redis.call('ZREMRANGEBYSCORE', key, 0, window_start)
        local count = redis.call('ZCARD', key)

        if count < max_messages then
            redis.call('ZADD', key, now, event_id)
            redis.call('EXPIRE', key, window_seconds)
            return 1
        else
            return 0
        end
        """
        
        result = await redis_client.eval(lua_script, 1, key, now, window_start, self.max_messages, event_id, self.window_seconds)
        return bool(result)

connection_limiter = ConnectionLimiter()
message_rate_limiter = MessageRateLimiter(
    max_messages=config.WS_MAX_MESSAGES_PER_MINUTE,
    window_seconds=60
)
