from langgraph_sdk import Auth

auth = Auth()


@auth.authenticate
async def authenticate(authorization: str | None):
    if not authorization:
        raise ValueError("Authorization header is missing.")

    print(f"Authorization header received: {authorization}")

    # 这里可以自定义校验逻辑
    # if authorization != "Bearer your_token":
    #     raise ValueError("Invalid authorization token.")

    # 返回 BaseUser 子类实例，identity 必填
    return {
        "identity": 1,
    }
