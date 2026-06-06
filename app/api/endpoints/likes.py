from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.api.dependencies import get_current_user
from app.scripts.db import get_db

router = APIRouter()

class LikeRequest(BaseModel):
    area_cd: str

@router.get("")
def get_likes(user=Depends(get_current_user), lang: str = "ko"):
    """내 좋아요 목록"""
    conn = get_db()
    cur = conn.cursor()
    try:
        name_col = "COALESCE(s.name_en, s.name)" if lang == "en" else "s.name"
        addr_col = "COALESCE(t.address_en, t.address)" if lang == "en" else "t.address"
        lvl_col = "COALESCE(c.congestion_level_en, c.congestion_level)" if lang == "en" else "c.congestion_level"

        # 💡 내부의 '#' 주석을 모두 제거한 깔끔한 SQL문
        cur.execute(f"""
            SELECT s.area_cd, {name_col}, s.category,
                   t.image_url, {addr_col}, {lvl_col}
            FROM likes l
            JOIN seoul_spots s ON l.area_cd = s.area_cd
            LEFT JOIN spot_mapping m ON s.area_cd = m.area_cd
            LEFT JOIN tour_spots t ON m.content_id = t.content_id
            LEFT JOIN (
                SELECT DISTINCT ON (area_cd) area_cd, congestion_level, congestion_level_en
                FROM congestion_data
                ORDER BY area_cd, updated_at DESC
            ) c ON s.area_cd = c.area_cd
            WHERE l.social_id = %s AND l.provider = %s
            ORDER BY l.created_at DESC
        """, (user["sub"], user["provider"]))
        rows = cur.fetchall()
        
        no_data_msg = "No Data" if lang == "en" else "데이터 없음"
        
        return [
            {
                "area_cd": r[0],
                "name": r[1],
                "category": r[2],
                "image_url": r[3],
                "address": r[4],
                "congestion_level": r[5] or no_data_msg
            }
            for r in rows
        ]
    finally:
        cur.close()
        conn.close()


@router.post("")
def add_like(body: LikeRequest, user=Depends(get_current_user)):
    """좋아요 추가"""
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO likes (social_id, provider, area_cd)
            VALUES (%s, %s, %s)
            ON CONFLICT (social_id, provider, area_cd) DO NOTHING
        """, (user["sub"], user["provider"], body.area_cd))
        conn.commit()
        return {"ok": True}
    finally:
        cur.close()
        conn.close()


@router.delete("/{area_cd}")
def remove_like(area_cd: str, user=Depends(get_current_user)):
    """좋아요 취소"""
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            DELETE FROM likes
            WHERE social_id = %s AND provider = %s AND area_cd = %s
        """, (user["sub"], user["provider"], area_cd))
        conn.commit()
        return {"ok": True}
    finally:
        cur.close()
        conn.close()


@router.get("/check/{area_cd}")
def check_like(area_cd: str, user=Depends(get_current_user)):
    """특정 장소 좋아요 여부 확인"""
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT 1 FROM likes
            WHERE social_id = %s AND provider = %s AND area_cd = %s
        """, (user["sub"], user["provider"], area_cd))
        return {"liked": cur.fetchone() is not None}
    finally:
        cur.close()
        conn.close()
