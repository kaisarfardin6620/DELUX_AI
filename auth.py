import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

import config

security = HTTPBearer()


def verify_token(token: str) -> int:
    """
    Verify a Django SimpleJWT access token.
      - Algorithm : HS256
      - Signing key: SECRET_KEY (identical to Django's SECRET_KEY in .env)
      - User claim : 'user_id'  (matches SIMPLE_JWT['USER_ID_CLAIM'] in Django settings)
    Returns the integer user_id on success, raises ValueError on failure.
    """
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("user_id")
        if user_id is None:
            raise ValueError("Token payload is missing the 'user_id' claim.")
        token_type = payload.get("token_type")
        if token_type != "access":
            raise ValueError("Only access tokens are accepted. Do not send a refresh token.")
        return int(user_id)
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired. Please log in again.")
    except jwt.InvalidTokenError as e:
        raise ValueError(f"Invalid token: {e}")


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> int:
    """FastAPI dependency for HTTP endpoints that require authentication."""
    try:
        return verify_token(credentials.credentials)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))