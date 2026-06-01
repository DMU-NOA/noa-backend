from fastapi import APIRouter, HTTPException
from app.scripts.db import get_db # DB 연결 함수가 있는 곳을 import하세요
import os
import requests

router = APIRouter()

@router.get("/spots")
def get_all_spots():
    conn = get_db()
    cur = conn.cursor()
    
    # 💡 3개 테이블 JOIN + 혼잡도 최신 데이터 JOIN
    query = """
        SELECT 
            s.area_cd, s.name, s.category, 
            t.image_url, t.description, t.address, 
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
                "congestion_level": row[6] if row[6] else "데이터 없음"
            })
        return {"data": results}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        cur.close()
        conn.close()

@router.get("/spots/search")
def search_spots(keyword: str):
    conn = get_db()
    cur = conn.cursor()
    
    # 1. 검색어 가공
    search_term = f"%{keyword}%"
    
    # 2. 메인 검색 쿼리 (이름, 설명, 테마 검색)
    search_query = """
        SELECT s.area_cd, s.name, s.category, t.image_url, t.address, t.description, c.congestion_level
        FROM seoul_spots s
        LEFT JOIN spot_mapping m ON s.area_cd = m.area_cd
        LEFT JOIN tour_spots t ON m.content_id = t.content_id
        LEFT JOIN congestion_data c ON s.area_cd = c.area_cd
        WHERE s.name LIKE %s OR t.description LIKE %s OR s.category LIKE %s
        ORDER BY c.updated_at DESC
    """
    
    # 3. 유사 테마 추천 쿼리 (가장 먼저 검색된 장소의 카테고리와 같은 것들)
    recommend_query = """
        SELECT s.area_cd, s.name, s.category, t.image_url, t.address
        FROM seoul_spots s
        LEFT JOIN spot_mapping m ON s.area_cd = m.area_cd
        LEFT JOIN tour_spots t ON m.content_id = t.content_id
        WHERE s.category = (SELECT category FROM seoul_spots WHERE name LIKE %s LIMIT 1)
        AND s.name NOT LIKE %s
        LIMIT 4
    """
    
    try:
        # 메인 검색 실행
        cur.execute(search_query, (search_term, search_term, search_term))
        rows = cur.fetchall()
        results = [{"area_cd": r[0], "name": r[1], "category": r[2], "image_url": r[3], "address": r[4], "description": r[5], "congestion_level": r[6]} for r in rows]
        
        # 추천 검색 실행 (검색 결과가 있을 때만)
        recommendations = []
        if results:
            cur.execute(recommend_query, (search_term, search_term))
            rec_rows = cur.fetchall()
            recommendations = [{"area_cd": r[0], "name": r[1], "category": r[2], "image_url": r[3], "address": r[4]} for r in rec_rows]
            
        return {"results": results, "recommendations": recommendations}
        
    finally:
        cur.close()
        conn.close()
        
@router.get("/spots/{area_cd}")
def get_spot_detail(area_cd: str):
    conn = get_db()
    cur = conn.cursor()
    
    query = """
        SELECT s.area_cd, s.name, s.category, t.image_url, t.description, t.address, c.congestion_level
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

@router.get("/spots/{area_cd}/alternatives")
def get_alternatives(area_cd: str):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT category FROM seoul_spots WHERE area_cd = %s", (area_cd,))
        row = cur.fetchone()
        if not row: return []
        category = row[0]

        query = """
            SELECT s.area_cd, s.name, s.category, t.image_url, t.description, t.address, c.congestion_level
            FROM seoul_spots s
            LEFT JOIN spot_mapping m ON s.area_cd = m.area_cd
            LEFT JOIN tour_spots t ON m.content_id = t.content_id
            LEFT JOIN (
                SELECT DISTINCT ON (area_cd) area_cd, congestion_level 
                FROM congestion_data 
                ORDER BY area_cd, updated_at DESC
            ) c ON s.area_cd = c.area_cd
            WHERE s.category = %s AND s.area_cd != %s
            ORDER BY 
                CASE c.congestion_level
                    WHEN '여유' THEN 1
                    WHEN '보통' THEN 2
                    WHEN '약간 붐빔' THEN 3
                    WHEN '붐빔' THEN 4
                    ELSE 5
                END ASC, 
                RANDOM() 
            LIMIT 4
        """
        cur.execute(query, (category, area_cd))
        rows = cur.fetchall()
        
        return [{"area_cd": r[0], "name": r[1], "category": r[2], "image_url": r[3], "description": r[4], "address": r[5], "congestion_level": r[6]} for r in rows]
    finally:
        cur.close()
        conn.close()

@router.get("/spots/{spot_id}/forecast")
def get_spot_forecast(spot_id: str):
    try:
        # 💡 서울시 API 키를 사용합니다. (.env 파일에 SEOUL_API_KEY가 있어야 합니다)
        SEOUL_API_KEY = os.getenv("SEOUL_API_KEY")
        if not SEOUL_API_KEY:
            raise ValueError("SEOUL_API_KEY가 설정되지 않았습니다.")

        # 💡 프론트엔드에서 넘어온 spot_id (예: POI009)를 그대로 URL에 넣습니다. (매핑 필요 없음!)
        url = f"http://openapi.seoul.go.kr:8088/{SEOUL_API_KEY}/json/citydata/1/5/{spot_id}"
        
        print(f"📡 [시간별 예측 API] 서울시 데이터 요청 중... ID: {spot_id}")
        
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
        
        # 💡 12시간 예측 데이터를 프론트엔드 차트용으로 가공합니다.
        for fcst in fcst_data:
            time_str = fcst.get("FCST_TIME", "")
            hour_label = time_str.split(" ")[1].split(":")[0] + "시" if time_str else ""
            
            lvl = fcst.get("FCST_CONGEST_LVL", "여유")
            
            # 💡 [핵심] 억지 비율 대신 '실제 최대 예측 인구수'를 추출합니다.
            pop = int(fcst.get("FCST_PPLTN_MAX", 0)) 
                
            forecast_list.append({
                "time": hour_label,
                "population": pop,  # 프론트엔드로 실제 인구수 전달
                "level": lvl
            })

        return {"forecast": forecast_list}
        
    except Exception as e:
        print(f"🚨 시간별 예측 API 에러: {e}")
        return {"forecast": []}

@router.get("/spots/{spot_id}/additional-info")
def get_spot_additional_info(spot_id: str):
    try:
        SEOUL_API_KEY = os.getenv("SEOUL_API_KEY")
        url = f"http://openapi.seoul.go.kr:8088/{SEOUL_API_KEY}/json/citydata/1/5/{spot_id}"
        
        print(f"📡 [부가정보 API - 상세버전] 서울시 데이터 요청 중... ID: {spot_id}")
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
            
            # 24시간 예보 추출
            fcst24_raw = w.get("FCST24HOURS", [])
            if isinstance(fcst24_raw, dict): fcst24_raw = [fcst24_raw]
            
            fcst24 = []
            for f in fcst24_raw:
                time_str = str(f.get("FCST_DT", ""))
                # YYYYMMDDHHMM 형식에서 HH시 추출
                hour = time_str[8:10] + "시" if len(time_str) >= 10 else "-"
                fcst24.append({
                    "time": hour,
                    "temp": f.get("TEMP", "-"),
                    "sky": f.get("SKY_STTS", "맑음"),
                    "rain_chance": f.get("RAIN_CHANCE", "0")
                })

            weather = {
                "temp": w.get("TEMP", "-"),
                "pm10": w.get("PM10_INDEX", "보통"),
                "pm10_val": w.get("PM10", "-"), # 실제 수치
                "pm25": w.get("PM25_INDEX", "보통"),
                "pm25_val": w.get("PM25", "-"), # 실제 수치
                "humidity": w.get("HUMIDITY", "-"),
                "msg": w.get("PCP_MSG", "맑음"),
                "forecast24": fcst24
            }

        # 2. 🚗 상세 교통 및 주차 현황
        traffic_data = citydata.get("ROAD_TRAFFIC_STTS", {})
        traffic = {
            "msg": "주변 도로 소통 정보가 없습니다.",
            "speed": "-"
        }
        if isinstance(traffic_data, dict) and "AVG_ROAD_DATA" in traffic_data:
            traffic["msg"] = traffic_data["AVG_ROAD_DATA"].get("ROAD_MSG", "원활")
            traffic["speed"] = traffic_data["AVG_ROAD_DATA"].get("ROAD_TRAFFIC_SPD", "-")

        parking_data = citydata.get("PRK_STTS", [])
        if isinstance(parking_data, dict): parking_data = [parking_data]
        
        parking_lots = []
        for p in parking_data:
            if p.get("PRK_NM"):
                parking_lots.append({
                    "name": p.get("PRK_NM"),
                    "cur": p.get("CUR_PRK_CNT", 0), # 빈자리
                    "max": p.get("CPCTY", 0),       # 총 주차면
                    "fee": p.get("RATES", 0)        # 기본요금
                })

        # 3. 🎪 문화/행사/축제 (기존과 동일)
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