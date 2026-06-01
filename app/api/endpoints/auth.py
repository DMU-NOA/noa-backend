import os
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import RedirectResponse
from app.services.auth_service import (
    create_jwt,
    decode_jwt,
    exchange_google_code,
    exchange_kakao_code,
    upsert_user,
)

load_dotenv()

router = APIRouter()

GOOGLE_AUTH_URL = (
    "https://accounts.google.com/o/oauth2/v2/auth"
    "?response_type=code"
    "&scope=openid%20email%20profile"
    "&client_id={client_id}"
    "&redirect_uri={redirect_uri}"
)

KAKAO_AUTH_URL = (
    "https://kauth.kakao.com/oauth/authorize"
    "?response_type=code"
    "&client_id={client_id}"
    "&redirect_uri={redirect_uri}"
)


# ── Google ──────────────────────────────────────────────

@router.get("/google")
def google_login():
    url = GOOGLE_AUTH_URL.format(
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        redirect_uri=f"{os.getenv('BACKEND_URL')}/auth/google/callback",
    )
    return RedirectResponse(url)


@router.get("/google/callback")
async def google_callback(code: str):
    try:
        user = await exchange_google_code(code)
        upsert_user(
            social_id=user["id"],
            provider="google",
            email=user.get("email", ""),
            name=user.get("name", ""),
        )
        token = create_jwt(
            user_id=user["id"],
            email=user.get("email", ""),
            name=user.get("name", ""),
            provider="google",
        )
        return RedirectResponse(f"{os.getenv('FRONTEND_URL')}/callback?token={token}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Google 로그인 실패: {str(e)}")


# ── Kakao ───────────────────────────────────────────────

@router.get("/kakao")
def kakao_login():
    url = KAKAO_AUTH_URL.format(
        client_id=os.getenv("KAKAO_CLIENT_ID"),
        redirect_uri=f"{os.getenv('BACKEND_URL')}/auth/kakao/callback",
    )
    return RedirectResponse(url)


@router.get("/kakao/callback")
async def kakao_callback(code: str):
    try:
        user = await exchange_kakao_code(code)
        upsert_user(
            social_id=user["id"],
            provider="kakao",
            email=user.get("email", ""),
            name=user.get("name", ""),
        )
        token = create_jwt(
            user_id=user["id"],
            email=user.get("email", ""),
            name=user.get("name", ""),
            provider="kakao",
        )
        return RedirectResponse(f"{os.getenv('FRONTEND_URL')}/callback?token={token}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Kakao 로그인 실패: {str(e)}")


# ── 현재 유저 정보 ───────────────────────────────────────

@router.get("/me")
def get_me(authorization: str = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="인증 토큰이 없습니다.")
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_jwt(token)
        return {
            "id": payload["sub"],
            "email": payload["email"],
            "name": payload["name"],
            "provider": payload["provider"],
        }
    except Exception:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
