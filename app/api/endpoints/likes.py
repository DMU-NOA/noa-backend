from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from app.api.dependencies import get_current_user
from app.scripts.db import get_db


router = APIRouter()


class LikeRequest(BaseModel):
    spot_id: str
    area_cd: Optional[str] = None
    content_id: str


@router.get("")
def get_likes(user=Depends(get_current_user), lang: str = "ko"):
    """내 좋아요 목록"""
    conn = get_db()
    cur = conn.cursor()

    try:
        if lang == "en":
            name_col = """
                CASE
                    WHEN l.area_cd IS NOT NULL
                    THEN COALESCE(s.name_en, s.name, t.name_en, t.name)
                    ELSE COALESCE(t.name_en, t.name)
                END
            """

            address_col = "COALESCE(t.address_en, t.address)"

        else:
            name_col = """
                CASE
                    WHEN l.area_cd IS NOT NULL
                    THEN COALESCE(s.name, t.name)
                    ELSE t.name
                END
            """

            address_col = "t.address"

        cur.execute(
            f"""
            SELECT
                COALESCE(l.area_cd, l.content_id) AS spot_id,
                l.area_cd,
                l.content_id,

                {name_col} AS name,

                CASE
                    WHEN l.area_cd IS NOT NULL
                    THEN COALESCE(s.category, t.category)
                    ELSE t.category
                END AS category,

                t.image_url,
                {address_col} AS address,

                lc.congestion_level,
                lc.source

            FROM likes l

            JOIN tour_spots t
                ON l.content_id = t.content_id

            LEFT JOIN seoul_spots s
                ON l.area_cd = s.area_cd

            LEFT JOIN latest_congestion lc
                ON l.content_id = lc.content_id

            WHERE
                l.social_id = %s
                AND l.provider = %s

            ORDER BY l.created_at DESC
            """,
            (
                user["sub"],
                user["provider"]
            )
        )

        rows = cur.fetchall()

        no_data_msg = (
            "No Data"
            if lang == "en"
            else "데이터 없음"
        )

        return [
            {
                "spot_id": row[0],
                "area_cd": row[1],
                "content_id": row[2],

                "name": row[3],
                "category": row[4],

                "image_url": row[5],
                "address": row[6],

                "congestion_level": (
                    row[7]
                    if row[7]
                    else no_data_msg
                ),

                "congestion_source": row[8]
            }
            for row in rows
        ]

    finally:
        cur.close()
        conn.close()


@router.post("")
def add_like(
    body: LikeRequest,
    user=Depends(get_current_user)
):
    """좋아요 추가"""

    conn = get_db()
    cur = conn.cursor()

    try:
        # content_id 기준 중복 확인
        cur.execute(
            """
            SELECT 1
            FROM likes
            WHERE
                social_id = %s
                AND provider = %s
                AND content_id = %s
            """,
            (
                user["sub"],
                user["provider"],
                body.content_id
            )
        )

        exists = cur.fetchone()

        if exists:
            return {"ok": True}

        cur.execute(
            """
            INSERT INTO likes (
                social_id,
                provider,
                area_cd,
                content_id
            )
            VALUES (%s, %s, %s, %s)
            """,
            (
                user["sub"],
                user["provider"],
                body.area_cd,
                body.content_id
            )
        )

        conn.commit()

        return {
            "ok": True,
            "spot_id": body.spot_id
        }

    finally:
        cur.close()
        conn.close()


@router.delete("/{spot_id}")
def remove_like(
    spot_id: str,
    user=Depends(get_current_user)
):
    """좋아요 취소"""

    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            DELETE FROM likes
            WHERE
                social_id = %s
                AND provider = %s
                AND (
                    area_cd = %s
                    OR content_id = %s
                )
            """,
            (
                user["sub"],
                user["provider"],
                spot_id,
                spot_id
            )
        )

        conn.commit()

        return {"ok": True}

    finally:
        cur.close()
        conn.close()


@router.get("/check/{spot_id}")
def check_like(
    spot_id: str,
    user=Depends(get_current_user)
):
    """특정 장소 좋아요 여부 확인"""

    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT 1
            FROM likes
            WHERE
                social_id = %s
                AND provider = %s
                AND (
                    area_cd = %s
                    OR content_id = %s
                )
            """,
            (
                user["sub"],
                user["provider"],
                spot_id,
                spot_id
            )
        )

        return {
            "liked": cur.fetchone() is not None
        }

    finally:
        cur.close()
        conn.close()