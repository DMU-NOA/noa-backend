# app/api/endpoints/chat.py
import os
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import OpenAI
from app.scripts.db import get_db

router = APIRouter()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class ChatRequest(BaseModel):
    message: str
    lat: float = None
    lng: float = None

@router.post("/")
async def chat_with_ai(req: ChatRequest):
    conn = get_db()
    cur = conn.cursor()
    # 💡 1. 이미지 URL과 area_cd도 가져오도록 SQL 수정
    cur.execute("""
        SELECT t.name, c.congestion_level, m.area_cd, t.image_url
        FROM tour_spots t
        JOIN spot_mapping m ON t.content_id = m.content_id
        JOIN congestion_data c ON m.area_cd = c.area_cd
        WHERE c.congestion_level IN ('여유', '보통')
        ORDER BY RANDOM()
        LIMIT 3
    """)
    candidates = cur.fetchall()
    cur.close()
    conn.close()

    if not candidates:
        return {"reply": "현재 추천해 드릴 만한 여유로운 장소가 파악되지 않네요 😭 잠시 후 다시 시도해 주세요!"}

    # 2. AI에게 넘겨줄 정보 세팅
    candidate_info = "\n".join([f"- ID: {area_cd} | 이름: {name} | 혼잡도: {lvl} | 이미지: {img}" for name, lvl, area_cd, img in candidates])

    # 💡 3. AI가 텍스트가 아닌 JSON으로 대답하도록 프롬프트 강력 통제
    system_prompt = f"""
    너는 서울 여행을 도와주는 친절하고 센스 있는 AI 비서 'NOA'야.
    사용자의 질문을 읽고, 아래에 제공된 [현재 쾌적한 장소 후보] 중에서 가장 적절한 1곳을 골라 추천해 줘.
    
    [현재 쾌적한 장소 후보]
    {candidate_info}
    
    규칙:
    1. 데이터(혼잡도, 테마 등)를 바탕으로 왜 이곳을 추천하는지 친절하게 설명할 것.
    2. 반드시 아래의 JSON 형식으로만 응답할 것. 절대 다른 텍스트를 덧붙이지 마.
    
    {{
        "reply": "비 오는 날에는 목동사격장을 추천할게요! 현재 혼잡도도 여유롭고...",
        "spot": {{
            "area_cd": "선택한장소ID",
            "name": "선택한장소이름",
            "image_url": "선택한장소이미지URL"
        }}
    }}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={ "type": "json_object" }, # 💡 무조건 JSON으로 반환하도록 강제
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": req.message}
            ]
        )
        # 문자열을 파이썬 딕셔너리로 변환하여 바로 리턴!
        ai_result = json.loads(response.choices[0].message.content)
        return ai_result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 연결 오류: {str(e)}")