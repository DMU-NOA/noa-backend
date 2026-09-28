"""서울 여행 취향 밸런스 게임. 실행: uvicorn balance.travel_balance_game:app --reload --port 8001"""
import os
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

app = FastAPI(title="NOA 여행 취향 밸런스 게임")

# 선택지의 tags는 관광지 설명·이름과 대조하는 취향 키워드입니다.
QUESTIONS = [
    {"title": "오늘 여행의 분위기는?", "choices": [
        {"label": "고즈넉한 역사 산책", "tags": ["역사", "궁궐", "전통", "문화재", "한옥"]},
        {"label": "감각적인 문화 탐방", "tags": ["미술", "전시", "박물관", "예술", "갤러리"]}]},
    {"title": "더 끌리는 공간은?", "choices": [
        {"label": "탁 트인 야외", "tags": ["공원", "산책", "숲", "하천", "정원"]},
        {"label": "편안한 실내", "tags": ["박물관", "미술관", "전시", "실내", "문화센터"]}]},
    {"title": "어떤 활동을 하고 싶나요?", "choices": [
        {"label": "동네 골목을 걸으며 발견하기", "tags": ["골목", "마을", "거리", "시장", "동네"]},
        {"label": "한곳에서 깊이 감상하기", "tags": ["박물관", "미술관", "문화재", "기념관", "전시"]}]},
    {"title": "여행의 속도는?", "choices": [
        {"label": "느긋하게 쉬어가기", "tags": ["공원", "숲", "정원", "산책", "휴식"]},
        {"label": "활기차게 구경하기", "tags": ["시장", "거리", "체험", "공연", "축제"]}]},
    {"title": "더 좋아하는 풍경은?", "choices": [
        {"label": "자연과 물가", "tags": ["한강", "하천", "공원", "숲", "산"]},
        {"label": "도시와 건축", "tags": ["건축", "한옥", "거리", "문화재", "도시"]}]},
    {"title": "여행에서 오래 기억할 것은?", "choices": [
        {"label": "사진으로 남길 풍경", "tags": ["전망", "공원", "정원", "한옥", "산책"]},
        {"label": "새롭게 배운 이야기", "tags": ["역사", "박물관", "기념관", "문화", "전시"]}]},
]

class Answers(BaseModel):
    choices: list[int] = Field(min_length=len(QUESTIONS), max_length=len(QUESTIONS))


def load_spots():
    """기존 NOA PostgreSQL의 tour_spots 테이블에서 실제 서울 관광지만 읽습니다."""
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
    if not all(os.getenv(key) for key in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")):
        raise HTTPException(status_code=503, detail="DB_HOST, DB_NAME, DB_USER, DB_PASSWORD를 noa-backend/.env에 설정하세요.")
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        with psycopg2.connect(host=os.getenv("DB_HOST"), dbname=os.getenv("DB_NAME"),
                              user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"),
                              port=os.getenv("DB_PORT", "5432"), connect_timeout=5) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""SELECT content_id AS id, name, address, description, image_url AS image
                               FROM tour_spots WHERE name IS NOT NULL
                                 AND address ILIKE '서울%'
                               ORDER BY content_id""")
                rows = [dict(row) for row in cur.fetchall()]
        return rows
    except psycopg2.Error as exc:
        raise HTTPException(status_code=503, detail="관광지 DB 연결 또는 tour_spots 조회에 실패했습니다. DB 설정과 테이블을 확인하세요.") from exc


def recommend(choices, spots):
    tags = [tag for index, answer in enumerate(choices) for tag in QUESTIONS[index]["choices"][answer]["tags"]]
    results = []
    for spot in spots:
        # TourAPI 설명은 HTML을 포함할 수 있어 텍스트로 정리한 뒤 추천 근거에만 활용합니다.
        searchable = re.sub(r"<[^>]+>", " ", f"{spot.get('name') or ''} {spot.get('description') or ''}").lower()
        matched = list(dict.fromkeys(tag for tag in tags if tag.lower() in searchable))
        if not matched:
            continue
        results.append({"id": str(spot["id"]), "name": spot["name"],
                        "address": spot.get("address") or "주소 정보 없음",
                        "image": spot.get("image"), "matched_tags": matched[:4],
                        "score": len(matched)})
    results.sort(key=lambda item: (-item["score"], item["name"]))
    return results[:5]


@app.get("/api/game/questions")
def questions():
    return [{"title": q["title"], "choices": [c["label"] for c in q["choices"]]} for q in QUESTIONS]


@app.post("/api/game/recommend")
def game_recommend(payload: Answers):
    if any(choice not in (0, 1) for choice in payload.choices):
        raise HTTPException(status_code=422, detail="각 문항은 0 또는 1을 선택해야 합니다.")
    spots = load_spots()
    return {"recommendations": recommend(payload.choices, spots), "demo": False,
            "message": "실제 관광지 DB의 이름·설명과 취향 키워드 일치도로 정렬했습니다. 혼잡도 예측 결과는 아닙니다."}


@app.get("/", response_class=HTMLResponse)
def game_page():
    return Path(__file__).with_name("travel_balance_game.html").read_text(encoding="utf-8")
