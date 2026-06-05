from fastapi import APIRouter, HTTPException
from app.scripts.db import get_db
import os
import requests
from openai import OpenAI # 💡 AI 연결을 위해 추가된 모듈

router = APIRouter()

@router.get("/spots")
def get_all_spots(lang: str = "ko"):
    conn = get_db()
    cur = conn.cursor()
    
    # 💡 다국어 지원: lang이 'en'이면 영문 컬럼을, 아니면 국문 컬럼을 가져옴
    name_col = "COALESCE(s.name_en, s.name)" if lang == "en" else "s.name"
    cat_col = "COALESCE(s.category_en, s.category)" if lang == "en" else "s.category"
    desc_col = "COALESCE(t.description_en, t.description)" if lang == "en" else "t.description"
    addr_col = "COALESCE(t.address_en, t.address)" if lang == "en" else "t.address"
    
    # 3개 테이블 JOIN + 혼잡도 최신 데이터 JOIN
    query = f"""
        SELECT 
            s.area_cd, {name_col}, {cat_col}, 
            t.image_url, {desc_col}, {addr_col}, 
            t.mapx, t.mapy,
            c.congestion_level
        FROM seoul_spots s
        LEFT JOIN spot_mapping m ON s.area_cd = m.area_cd
        LEFT JOIN tour_spots t ON m.content_id = t.content_id
        LEFT JOIN (
            SELECT DISTINCT ON (area_cd) area_cd, congestion_level 
            FROM congestion_data 
            ORDER BY area_cd, updated_at DESC
        ) c ON s.area_cd = c.area_cd;
    """
    
    try:
        cur.execute(query)
        rows = cur.fetchall()
        
        results = []
        for row in rows:
            results.append({
                "area_cd": row[0],
                "name": row[1],
                "category": row[2],
                "image_url": row[3],
                "description": row[4],
                "address": row[5],
                "mapx": float(row[6]) if row[6] else 0.0,
                "mapy": float(row[7]) if row[7] else 0.0,
                "congestion_level": row[8] if row[8] else "데이터 없음"
            })
        return {"data": results}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        cur.close()
        conn.close()

@router.get("/spots/search")
def search_spots(keyword: str, lang: str = "ko"):
    conn = get_db()
    cur = conn.cursor()
    
    search_term = f"%{keyword}%"
    
    name_col = "COALESCE(s.name_en, s.name)" if lang == "en" else "s.name"
    cat_col = "COALESCE(s.category_en, s.category)" if lang == "en" else "s.category"
    desc_col = "COALESCE(t.description_en, t.description)" if lang == "en" else "t.description"
    addr_col = "COALESCE(t.address_en, t.address)" if lang == "en" else "t.address"
    
    # 💡 검색은 한글이든 영어든 어느 컬럼에 걸려도 찾아지도록 확장!
    search_query = f"""
        SELECT s.area_cd, {name_col}, {cat_col}, t.image_url, {addr_col}, {desc_col}, c.congestion_level
        FROM seoul_spots s
        LEFT JOIN spot_mapping m ON s.area_cd = m.area_cd
        LEFT JOIN tour_spots t ON m.content_id = t.content_id
        LEFT JOIN congestion_data c ON s.area_cd = c.area_cd
        WHERE s.name LIKE %s OR s.name_en ILIKE %s 
           OR t.description LIKE %s OR t.description_en ILIKE %s 
           OR s.category LIKE %s OR s.category_en ILIKE %s
        ORDER BY c.updated_at DESC
    """
    
    recommend_query = f"""
        SELECT s.area_cd, {name_col}, {cat_col}, t.image_url, {addr_col}
        FROM seoul_spots s
        LEFT JOIN spot_mapping m ON s.area_cd = m.area_cd
        LEFT JOIN tour_spots t ON m.content_id = t.content_id
        WHERE s.category = (
            SELECT category FROM seoul_spots 
            WHERE name LIKE %s OR name_en ILIKE %s LIMIT 1
        )
        AND s.name NOT LIKE %s AND (s.name_en IS NULL OR s.name_en NOT ILIKE %s)
        LIMIT 4
    """
    
    try:
        cur.execute(search_query, (search_term, search_term, search_term, search_term, search_term, search_term))
        rows = cur.fetchall()
        results = [{"area_cd": r[0], "name": r[1], "category": r[2], "image_url": r[3], "address": r[4], "description": r[5], "congestion_level": r[6]} for r in rows]
        
        recommendations = []
        if results:
            cur.execute(recommend_query, (search_term, search_term, search_term, search_term))
            rec_rows = cur.fetchall()
            recommendations = [{"area_cd": r[0], "name": r[1], "category": r[2], "image_url": r[3], "address": r[4]} for r in rec_rows]
            
        return {"results": results, "recommendations": recommendations}
        
    finally:
        cur.close()
        conn.close()
        
@router.get("/spots/{area_cd}")
def get_spot_detail(area_cd: str, lang: str = "ko"):
    conn = get_db()
    cur = conn.cursor()
    
    name_col = "COALESCE(s.name_en, s.name)" if lang == "en" else "s.name"
    cat_col = "COALESCE(s.category_en, s.category)" if lang == "en" else "s.category"
    desc_col = "COALESCE(t.description_en, t.description)" if lang == "en" else "t.description"
    addr_col = "COALESCE(t.address_en, t.address)" if lang == "en" else "t.address"
    
    query = f"""
        SELECT s.area_cd, {name_col}, {cat_col}, t.image_url, {desc_col}, {addr_col}, c.congestion_level
        FROM seoul_spots s
        LEFT JOIN spot_mapping m ON s.area_cd = m.area_cd
        LEFT JOIN tour_spots t ON m.content_id = t.content_id
        LEFT JOIN congestion_data c ON s.area_cd = c.area_cd
        WHERE s.area_cd = %s
        ORDER BY c.updated_at DESC LIMIT 1;
    """
    
    try:
        cur.execute(query, (area_cd,))
        row = cur.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Spot not found")
            
        return {
            "area_cd": row[0],
            "name": row[1],
            "category": row[2],
            "image_url": row[3],
            "description": row[4],
            "address": row[5],
            "congestion_level": row[6] if row[6] else "데이터 없음"
        }
    finally:
        cur.close()
        conn.close()

# 💡 대안 장소 추천 API
@router.get("/spots/{area_cd}/alternatives")
def get_alternatives(area_cd: str, lang: str = "ko"):
    conn = get_db()
    cur = conn.cursor()
    try:
        name_col = "COALESCE(s.name_en, s.name)" if lang == "en" else "s.name"
        cat_col = "COALESCE(s.category_en, s.category)" if lang == "en" else "s.category"
        desc_col = "COALESCE(t.description_en, t.description)" if lang == "en" else "t.description"
        addr_col = "COALESCE(t.address_en, t.address)" if lang == "en" else "t.address"

        # 1. 원래 장소의 정보 가져오기 (언어에 맞춰서 AI에게 넘겨줌)
        cur.execute(f"""
            SELECT {name_col}, {cat_col}, {desc_col} 
            FROM seoul_spots s
            LEFT JOIN spot_mapping m ON s.area_cd = m.area_cd
            LEFT JOIN tour_spots t ON m.content_id = t.content_id
            WHERE s.area_cd = %s
        """, (area_cd,))
        origin = cur.fetchone()
        
        if not origin:
            return []
            
        origin_name, origin_cat, origin_desc = origin
        origin_desc = origin_desc if origin_desc else ""
        origin_info = f"Name: {origin_name}, Theme: {origin_cat}, Feature: {origin_desc[:100]}..." if lang == "en" else f"이름: {origin_name}, 테마: {origin_cat}, 특징: {origin_desc[:100]}..."

        # 2. 혼잡도 여유/보통 후보군 조회
        cur.execute(f"""
            SELECT s.area_cd, {name_col}, {cat_col} 
            FROM seoul_spots s
            JOIN congestion_data c ON s.area_cd = c.area_cd
            WHERE c.congestion_level IN ('여유', '보통') 
            AND s.area_cd != %s
        """, (area_cd,))
        candidates = cur.fetchall()

        if not candidates:
            return []

        candidate_text = "\n".join([f"ID: {c[0]} | Name/이름: {c[1]} | Theme/테마: {c[2]}" for c in candidates])

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        system_prompt = f"""
        You are a travel expert. The user's destination is crowded, so recommend exactly 4 alternatives from the [Candidate List] that have the most similar vibe, theme, and features.
        
        [Target Destination]
        {origin_info}

        [Candidate List]
        {candidate_text}

        Rules:
        1. Select ONLY IDs from the [Candidate List].
        2. DO NOT provide any other explanation. Just output 4 IDs separated by commas (e.g., POI002, POI015, POI102, POI111).
        """

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system_prompt}]
        )
        
        ai_reply = response.choices[0].message.content
        selected_ids = [aid.strip() for aid in ai_reply.split(",") if aid.strip()]

        if selected_ids:
            cur.execute(f"""
                SELECT s.area_cd, {name_col}, {cat_col}, t.image_url, {desc_col}, {addr_col}, c.congestion_level
                FROM seoul_spots s
                LEFT JOIN spot_mapping m ON s.area_cd = m.area_cd
                LEFT JOIN tour_spots t ON m.content_id = t.content_id
                LEFT JOIN congestion_data c ON s.area_cd = c.area_cd
                WHERE s.area_cd IN %s
            """, (tuple(selected_ids),))
            
            rows = cur.fetchall()
            return [{"area_cd": r[0], "name": r[1], "category": r[2], "image_url": r[3], "description": r[4], "address": r[5], "congestion_level": r[6]} for r in rows]
        else:
            return []

    except Exception as e:
        print(f"🚨 AI 대안 관광지 추천 에러: {e}")
        return []
        
    finally:
        cur.close()
        conn.close()

@router.get("/spots/{spot_id}/forecast")
def get_spot_forecast(spot_id: str, lang: str = "ko"):
    try:
        SEOUL_API_KEY = os.getenv("SEOUL_API_KEY")
        if not SEOUL_API_KEY:
            raise ValueError("SEOUL_API_KEY가 설정되지 않았습니다.")

        # 💡 다국어 지원: 언어에 따라 국문/영문 API 엔드포인트 분기처리!
        seoul_api_type = "citydata_eng" if lang == "en" else "citydata"
        url = f"http://openapi.seoul.go.kr:8088/{SEOUL_API_KEY}/json/{seoul_api_type}/1/5/{spot_id}"
        
        res = requests.get(url, timeout=10)
        data = res.json()
        
        citydata = data.get("CITYDATA", {})
        if not citydata:
            return {"forecast": []}
            
        live_ppltn = citydata.get("LIVE_PPLTN_STTS", [])
        if not live_ppltn:
            return {"forecast": []}
            
        fcst_data = live_ppltn[0].get("FCST_PPLTN", [])
        forecast_list = []
        
        for fcst in fcst_data:
            time_str = fcst.get("FCST_TIME", "")
            hour_label = time_str.split(" ")[1].split(":")[0] + ("시" if lang == "ko" else ":00") if time_str else ""
            
            # 영문 API는 Crowded, Normal 등으로 옵니다.
            lvl = fcst.get("FCST_CONGEST_LVL", "여유")
            pop = int(fcst.get("FCST_PPLTN_MAX", 0)) 
                
            forecast_list.append({
                "time": hour_label,
                "population": pop,
                "level": lvl
            })

        return {"forecast": forecast_list}
        
    except Exception as e:
        print(f"🚨 시간별 예측 API 에러: {e}")
        return {"forecast": []}

@router.get("/spots/{spot_id}/additional-info")
def get_spot_additional_info(spot_id: str, lang: str = "ko"):
    try:
        SEOUL_API_KEY = os.getenv("SEOUL_API_KEY")
        seoul_api_type = "citydata_eng" if lang == "en" else "citydata"
        url = f"http://openapi.seoul.go.kr:8088/{SEOUL_API_KEY}/json/{seoul_api_type}/1/5/{spot_id}"
        
        res = requests.get(url, timeout=10)
        data = res.json()
        citydata = data.get("CITYDATA", {})
        
        if not citydata:
            return {"weather": None, "traffic": None, "parking_lots": [], "events": []}

        # 1. 🌤️ 24시간 날씨 및 상세 미세먼지
        weather_data = citydata.get("WEATHER_STTS", [])
        weather = None
        if weather_data:
            w = weather_data[0]
            fcst24_raw = w.get("FCST24HOURS", [])
            if isinstance(fcst24_raw, dict): fcst24_raw = [fcst24_raw]
            
            fcst24 = []
            for f in fcst24_raw:
                time_str = str(f.get("FCST_DT", ""))
                hour = time_str[8:10] + ("시" if lang == "ko" else ":00") if len(time_str) >= 10 else "-"
                fcst24.append({
                    "time": hour,
                    "temp": f.get("TEMP", "-"),
                    "sky": f.get("SKY_STTS", "Clear"),
                    "rain_chance": f.get("RAIN_CHANCE", "0")
                })

            weather = {
                "temp": w.get("TEMP", "-"),
                "pm10": w.get("PM10_INDEX", "-"),
                "pm10_val": w.get("PM10", "-"), 
                "pm25": w.get("PM25_INDEX", "-"),
                "pm25_val": w.get("PM25", "-"), 
                "humidity": w.get("HUMIDITY", "-"),
                "msg": w.get("PCP_MSG", "") if lang == "en" else w.get("WEATHER_MSG", "맑음"),
                "forecast24": fcst24
            }

        # 2. 🚗 상세 교통 및 주차 현황
        traffic_data = citydata.get("ROAD_TRAFFIC_STTS", {})
        traffic = {
            "msg": "No traffic info." if lang == "en" else "주변 도로 소통 정보가 없습니다.",
            "speed": "-"
        }
        if isinstance(traffic_data, dict) and "AVG_ROAD_DATA" in traffic_data:
            traffic["msg"] = traffic_data["AVG_ROAD_DATA"].get("ROAD_MSG", "Smooth" if lang == "en" else "원활")
            traffic["speed"] = traffic_data["AVG_ROAD_DATA"].get("ROAD_TRAFFIC_SPD", "-")

        parking_data = citydata.get("PRK_STTS", [])
        if isinstance(parking_data, dict): parking_data = [parking_data]
        
        parking_lots = []
        for p in parking_data:
            if p.get("PRK_NM"):
                parking_lots.append({
                    "name": p.get("PRK_NM"),
                    "cur": p.get("CUR_PRK_CNT", 0),
                    "max": p.get("CPCTY", 0),       
                    "fee": p.get("RATES", 0)        
                })

        # 3. 🎪 문화/행사/축제
        event_data = citydata.get("CULTURALEVENTINFO", [])
        if isinstance(event_data, dict): event_data = [event_data]
            
        events = []
        for ev in event_data:
            if ev.get("EVENT_NM"):
                events.append({
                    "name": ev.get("EVENT_NM"),
                    "period": ev.get("EVENT_PERIOD", ""),
                    "place": ev.get("EVENT_PLACE", "")
                })

        return {
            "weather": weather,
            "traffic": traffic,
            "parking_lots": parking_lots,
            "events": events
        }
        
    except Exception as e:
        print(f"🚨 부가정보 상세 API 에러: {e}")
        return {"weather": None, "traffic": None, "parking_lots": [], "events": []}