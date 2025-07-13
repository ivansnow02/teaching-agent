import os
from langgraph_sdk import Auth
import redis.asyncio as aioredis

auth = Auth()
redis_client = aioredis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=int(os.getenv("REDIS_DB", 0)),
    password=os.getenv("REDIS_PASSWORD", ""),
    decode_responses=True,
)


async def get_user_id(authorization: str | None):
    if not authorization:
        return None

    # 从 Redis 中获取用户 ID
    user_id = await redis_client.get(f"login:token:{authorization}")

    print(f"Retrieved user ID from Redis: {user_id}")
    return user_id


@auth.authenticate
async def authenticate(authorization: str | None):
    if not authorization:
        raise ValueError("Authorization header is missing.")

    print(f"Authorization header received: {authorization}")

    # 这里可以自定义校验逻辑
    # if authorization != "Bearer your_token":
    #     raise ValueError("Invalid authorization token.")

    # 获取用户 ID
    user_id = await get_user_id(authorization)
    if not user_id:
        raise ValueError("User ID not found for the provided authorization.")
    print(f"User ID retrieved: {user_id}")
    # 返回 BaseUser 子类实例，identity 必填
    return {"identity": user_id, "authorization": authorization}
