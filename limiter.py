import time
import uuid
from redis.asyncio import Redis
import config

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
        event_id = uuid.uuid4().hex

        pipeline = redis_client.pipeline()
        pipeline.zremrangebyscore(key, 0, now - self.window_seconds)
        pipeline.zcard(key)
        results = await pipeline.execute()
        current_message_count = results[1]

        if current_message_count >= self.max_messages:
            return False

        pipeline = redis_client.pipeline()
        pipeline.zadd(key, {event_id: now})
        pipeline.expire(key, self.window_seconds)
        await pipeline.execute()
        return True

connection_limiter = ConnectionLimiter()
message_rate_limiter = MessageRateLimiter(
    max_messages=config.WS_MAX_MESSAGES_PER_MINUTE,
    window_seconds=60
)