import os
import httpx
from datetime import datetime, timedelta
from dotenv import load_dotenv
from jose import jwt
from app.scripts.db import get_db

load_dotenv()


def upsert_user(social_id: str, provider: str, email: str, name: str) -> dict:
    """유저가 없으면 생성, 있으면 정보 업데이트 후 반환"""
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO users (social_id, provider, email, name)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (social_id, provider)
            DO UPDATE SET email = EXCLUDED.email, name = EXCLUDED.name
            RETURNING id, social_id, provider, email, name, created_at
        """, (social_id, provider, email, name))
        row = cur.fetchone()
        conn.commit()
        return {
            "id": row[0],
            "social_id": row[1],
            "provider": row[2],
            "email": row[3],
            "name": row[4],
            "created_at": str(row[5]),
        }
    finally:
        cur.close()
        conn.close()


def create_jwt(user_id: str, email: str, name: str, provider: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "name": name,
        "provider": provider,
        "exp": datetime.utcnow() + timedelta(minutes=int(os.getenv("JWT_EXPIRE_MINUTES", 60 * 24 * 7))),
    }
    return jwt.encode(payload, os.getenv("JWT_SECRET_KEY"), algorithm=os.getenv("JWT_ALGORITHM", "HS256"))


def decode_jwt(token: str) -> dict:
    return jwt.decode(token, os.getenv("JWT_SECRET_KEY"), algorithms=[os.getenv("JWT_ALGORITHM", "HS256")])


async def exchange_google_code(code: str) -> dict:
    """Google authorization code → 유저 정보"""
    async with httpx.AsyncClient() as client:
        # 1. code → access_token
        token_res = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                "redirect_uri": f"{os.getenv('BACKEND_URL')}/auth/google/callback",
                "grant_type": "authorization_code",
            },
        )
        token_res.raise_for_status()
        access_token = token_res.json()["access_token"]

        # 2. access_token → 유저 정보
        user_res = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_res.raise_for_status()
        return user_res.json()  # id, email, name, picture


async def exchange_kakao_code(code: str) -> dict:
    """Kakao authorization code → 유저 정보"""
    async with httpx.AsyncClient() as client:
        # 1. code → access_token
        token_data = {
            "grant_type": "authorization_code",
            "client_id": os.getenv("KAKAO_CLIENT_ID"),
            "redirect_uri": f"{os.getenv('BACKEND_URL')}/auth/kakao/callback",
            "code": code,
        }
        kakao_secret = os.getenv("KAKAO_CLIENT_SECRET")
        if kakao_secret:
            token_data["client_secret"] = kakao_secret

        token_res = await client.post(
            "https://kauth.kakao.com/oauth/token",
            data=token_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        token_res.raise_for_status()
        access_token = token_res.json()["access_token"]

        # 2. access_token → 유저 정보
        user_res = await client.get(
            "https://kapi.kakao.com/v2/user/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_res.raise_for_status()
        data = user_res.json()

        kakao_account = data.get("kakao_account", {})
        profile = kakao_account.get("profile", {})
        email = kakao_account.get("email", "")
        name = (
            profile.get("nickname")
            or profile.get("profile_nickname")
            or (email.split("@")[0] if email else "카카오유저")
        )
        return {
            "id": str(data["id"]),
            "email": email,
            "name": name,
            "picture": profile.get("profile_image_url", ""),
        }
