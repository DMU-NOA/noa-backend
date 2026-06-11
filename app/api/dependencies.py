from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from app.services.auth_service import decode_jwt

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """JWT 토큰 검증 의존성 - /api/* 보호용"""
    try:
        return decode_jwt(token)
    except Exception:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
