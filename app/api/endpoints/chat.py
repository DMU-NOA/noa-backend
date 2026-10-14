"""NOA chat recommendations based on the same latest_congestion source as spot cards."""
import json
import logging
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import OpenAI
from app.scripts.db import get_db

router = APIRouter()
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str
    lat: float | None = None
    lng: float | None = None
    lang: str = "ko"


def _candidates(lang: str):
    """Use current spot records, not legacy congestion_data or a nonexistent _en column."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(NULLIF(t.name_en, ''), t.name)
                           AS display_name_en,
                       t.name, t.content_id, m.area_cd, t.image_url,
                       l.congestion_level
                FROM latest_congestion l
                JOIN tour_spots t ON t.content_id = l.content_id
                LEFT JOIN spot_mapping m ON m.content_id = t.content_id
                WHERE l.congestion_level IN ('여유', '보통')
                  AND t.name IS NOT NULL
                ORDER BY
                  CASE WHEN l.source = 'actual' THEN 0 ELSE 1 END,
                  t.content_id
                LIMIT 50
                """
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    return [
        {
            "spot_id": str(content_id),
            "area_cd": str(content_id),
            "name": name_en if lang == "en" else name,
            "image_url": image_url,
            "congestion_level": level,
        }
        for name_en, name, content_id, _area_cd, image_url, level in rows
    ]


def _fallback(candidates, lang):
    if not candidates:
        return {"reply": (
            "There are no uncrowded locations to recommend from the available data."
            if lang == "en" else "현재 저장된 혼잡도 데이터에서 추천할 여유로운 장소를 찾지 못했습니다."
        ), "spot": None}
    return {
        "reply": (
            "AI recommendations are temporarily unavailable. Here is a place selected from the stored congestion data."
            if lang == "en" else
            "AI 추천을 잠시 이용할 수 없어 저장된 혼잡도 데이터를 기준으로 장소를 안내해 드립니다."
        ),
        "spot": candidates[0],
    }


@router.post("/")
async def chat_with_ai(req: ChatRequest):
    try:
        candidates = _candidates(req.lang)
    except Exception:
        logger.exception("Chat candidate database lookup failed")
        raise HTTPException(status_code=503, detail="추천 데이터를 일시적으로 조회할 수 없습니다.")

    if not candidates:
        return _fallback(candidates, req.lang)

    # Only candidate IDs from the database can become a recommended spot.
    sample = candidates[:12]
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        logger.warning("Chat OpenAI key missing; returning DB-based recommendation")
        return _fallback(sample, req.lang)

    descriptions = "\n".join(
        f"ID: {c['spot_id']} | Name: {c['name']} | Congestion: {c['congestion_level']}"
        for c in sample
    )
    system = (
        "You are NOA, a Seoul travel assistant. Respond in English."
        if req.lang == "en" else
        "너는 서울 여행 도우미 NOA다. 친절하게 한국어로 답변해."
    )
    system += (
        "\nPick exactly one location from these real candidate records and do not invent an ID. "
        "Return a JSON object with keys reply (helpful answer to the user) "
        "and spot_id (one candidate ID).\nCandidates:\n" + descriptions
    )
    try:
        response = OpenAI(api_key=key).chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": req.message},
            ],
            timeout=20,
        )
        result = json.loads(response.choices[0].message.content or "{}")
        chosen = next((c for c in sample if c["spot_id"] == str(result.get("spot_id"))), None)
        if chosen and isinstance(result.get("reply"), str) and result["reply"].strip():
            return {"reply": result["reply"], "spot": chosen}
        logger.warning("Chat AI returned invalid candidate; using DB fallback")
    except Exception:
        logger.exception("Chat OpenAI request failed; using DB fallback")

    return _fallback(sample, req.lang)
