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

    try:
        if lang == "en":
            name_col = """
                CASE
                    WHEN l.source = 'actual'
                    THEN COALESCE(s.name_en, s.name, t.name_en, t.name)
                    ELSE COALESCE(t.name_en, t.name)
                END
            """

            cat_col = """
                CASE
                    WHEN l.source = 'actual'
                    THEN COALESCE(s.category_en, s.category, t.category)
                    ELSE t.category
                END
            """

            desc_col = "COALESCE(t.description_en, t.description)"
            addr_col = "COALESCE(t.address_en, t.address)"

        else:
            name_col = """
                CASE
                    WHEN l.source = 'actual'
                    THEN COALESCE(s.name, t.name)
                    ELSE t.name
                END
            """

            cat_col = """
                CASE
                    WHEN l.source = 'actual'
                    THEN COALESCE(s.category, t.category)
                    ELSE t.category
                END
            """

            desc_col = "t.description"
            addr_col = "t.address"

        query = f"""
            SELECT
                COALESCE(l.area_cd, t.content_id) AS spot_id,

                l.area_cd,
                t.content_id,

                {name_col} AS name,
                {cat_col} AS category,

                t.image_url,
                {desc_col} AS description,
                {addr_col} AS address,

                t.mapx,
                t.mapy,

                l.congestion_level,
                l.source,
                l.updated_at

            FROM latest_congestion l

            JOIN tour_spots t
                ON l.content_id = t.content_id

            LEFT JOIN seoul_spots s
                ON l.area_cd = s.area_cd

            ORDER BY name
        """

        cur.execute(query)
        rows = cur.fetchall()

        results = []

        for row in rows:
            results.append({
                "spot_id": row[0],
                "area_cd": row[1],
                "content_id": row[2],

                "name": row[3],
                "category": row[4],

                "image_url": row[5],
                "description": row[6],
                "address": row[7],

                "mapx": float(row[8]) if row[8] else 0.0,
                "mapy": float(row[9]) if row[9] else 0.0,

                "congestion_level": row[10] or "데이터 없음",
                "congestion_source": row[11],

                "updated_at": (
                    row[12].isoformat()
                    if row[12]
                    else None
                )
            })

        return {
            "count": len(results),
            "data": results
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    finally:
        cur.close()
        conn.close()

@router.get("/spots/search")
def search_spots(keyword: str, lang: str = "ko"):
    conn = get_db()
    cur = conn.cursor()

    try:
        search_term = f"%{keyword}%"

        if lang == "en":
            name_col = """
                CASE
                    WHEN l.source = 'actual'
                    THEN COALESCE(s.name_en, s.name, t.name_en, t.name)
                    ELSE COALESCE(t.name_en, t.name)
                END
            """

            desc_col = "COALESCE(t.description_en, t.description)"
            addr_col = "COALESCE(t.address_en, t.address)"

        else:
            name_col = """
                CASE
                    WHEN l.source = 'actual'
                    THEN COALESCE(s.name, t.name)
                    ELSE t.name
                END
            """

            desc_col = "t.description"
            addr_col = "t.address"

        query = f"""
            SELECT
                COALESCE(l.area_cd, t.content_id) AS spot_id,
                l.area_cd,
                t.content_id,

                {name_col} AS name,
                COALESCE(s.category, t.category) AS category,

                t.image_url,
                {desc_col} AS description,
                {addr_col} AS address,

                t.mapx,
                t.mapy,

                l.congestion_level,
                l.source

            FROM latest_congestion l

            JOIN tour_spots t
                ON l.content_id = t.content_id

            LEFT JOIN seoul_spots s
                ON l.area_cd = s.area_cd

            WHERE
                COALESCE(s.name, '') ILIKE %s
                OR COALESCE(s.name_en, '') ILIKE %s
                OR COALESCE(t.name, '') ILIKE %s
                OR COALESCE(t.name_en, '') ILIKE %s
                OR COALESCE(t.description, '') ILIKE %s
                OR COALESCE(t.description_en, '') ILIKE %s
                OR COALESCE(s.category, '') ILIKE %s
                OR COALESCE(t.category, '') ILIKE %s

            ORDER BY name
        """

        cur.execute(
            query,
            (
                search_term,
                search_term,
                search_term,
                search_term,
                search_term,
                search_term,
                search_term,
                search_term,
            )
        )

        rows = cur.fetchall()

        results = []

        for row in rows:
            results.append({
                "spot_id": row[0],
                "area_cd": row[1],
                "content_id": row[2],

                "name": row[3],
                "category": row[4],

                "image_url": row[5],
                "description": row[6],
                "address": row[7],

                "mapx": float(row[8]) if row[8] else 0.0,
                "mapy": float(row[9]) if row[9] else 0.0,

                "congestion_level": row[10] or "데이터 없음",
                "congestion_source": row[11],
            })

        return {
            "results": results,
            "recommendations": []
        }

    finally:
        cur.close()
        conn.close()
        
@router.get("/spots/{spot_id}")
def get_spot_detail(spot_id: str, lang: str = "ko"):
    conn = get_db()
    cur = conn.cursor()

    try:
        if lang == "en":
            name_col = """
                CASE
                    WHEN l.source = 'actual'
                    THEN COALESCE(s.name_en, s.name, t.name_en, t.name)
                    ELSE COALESCE(t.name_en, t.name)
                END
            """

            cat_col = """
                CASE
                    WHEN l.source = 'actual'
                    THEN COALESCE(s.category_en, s.category, t.category)
                    ELSE t.category
                END
            """

            desc_col = "COALESCE(t.description_en, t.description)"
            addr_col = "COALESCE(t.address_en, t.address)"

        else:
            name_col = """
                CASE
                    WHEN l.source = 'actual'
                    THEN COALESCE(s.name, t.name)
                    ELSE t.name
                END
            """

            cat_col = """
                CASE
                    WHEN l.source = 'actual'
                    THEN COALESCE(s.category, t.category)
                    ELSE t.category
                END
            """

            desc_col = "t.description"
            addr_col = "t.address"

        query = f"""
            SELECT
                COALESCE(l.area_cd, t.content_id) AS spot_id,

                l.area_cd,
                t.content_id,

                {name_col} AS name,
                {cat_col} AS category,

                t.image_url,
                {desc_col} AS description,
                {addr_col} AS address,

                t.mapx,
                t.mapy,

                l.congestion_level,
                l.source,
                l.updated_at

            FROM latest_congestion l

            JOIN tour_spots t
                ON l.content_id = t.content_id

            LEFT JOIN seoul_spots s
                ON l.area_cd = s.area_cd

            WHERE
                (
                    l.source = 'actual'
                    AND l.area_cd = %s
                )

                OR

                (
                    l.source = 'predicted'
                    AND t.content_id = %s
                )

            LIMIT 1
        """

        cur.execute(
            query,
            (
                spot_id,
                spot_id
            )
        )

        row = cur.fetchone()

        if not row:
            raise HTTPException(
                status_code=404,
                detail="Spot not found"
            )

        return {
            "spot_id": row[0],
            "area_cd": row[1],
            "content_id": row[2],

            "name": row[3],
            "category": row[4],

            "image_url": row[5],
            "description": row[6],
            "address": row[7],

            "mapx": float(row[8]) if row[8] else 0.0,
            "mapy": float(row[9]) if row[9] else 0.0,

            "congestion_level": row[10] or "데이터 없음",
            "congestion_source": row[11],

            "updated_at": (
                row[12].isoformat()
                if row[12]
                else None
            )
        }

    finally:
        cur.close()
        conn.close()

# 💡 대안 장소 추천 API
@router.get("/spots/{spot_id}/alternatives")
def get_alternatives(spot_id: str, lang: str = "ko"):
    conn = get_db()
    cur = conn.cursor()

    try:
        # actual: spot_id = area_cd
        # predicted: spot_id = content_id
        if lang == "en":
            name_expr = """
                CASE
                    WHEN l.source = 'actual'
                    THEN COALESCE(s.name_en, s.name, t.name_en, t.name)
                    ELSE COALESCE(t.name_en, t.name)
                END
            """
            category_expr = """
                CASE
                    WHEN l.source = 'actual'
                    THEN COALESCE(s.category_en, s.category, t.category)
                    ELSE t.category
                END
            """
            description_expr = "COALESCE(t.description_en, t.description)"
            address_expr = "COALESCE(t.address_en, t.address)"
        else:
            name_expr = """
                CASE
                    WHEN l.source = 'actual'
                    THEN COALESCE(s.name, t.name)
                    ELSE t.name
                END
            """
            category_expr = """
                CASE
                    WHEN l.source = 'actual'
                    THEN COALESCE(s.category, t.category)
                    ELSE t.category
                END
            """
            description_expr = "t.description"
            address_expr = "t.address"

        # 1. 기준 관광지 조회
        cur.execute(
            f"""
            SELECT
                CASE
                    WHEN l.source = 'actual'
                    THEN l.area_cd
                    ELSE l.content_id
                END AS spot_id,
                l.area_cd,
                l.content_id,
                {name_expr} AS name,
                {category_expr} AS category,
                {description_expr} AS description,
                t.mapx,
                t.mapy
            FROM latest_congestion l
            JOIN tour_spots t
                ON l.content_id = t.content_id
            LEFT JOIN seoul_spots s
                ON l.area_cd = s.area_cd
            WHERE
                (
                    (l.source = 'actual' AND l.area_cd = %s)
                    OR
                    (l.source = 'predicted' AND l.content_id = %s)
                )
            LIMIT 1
            """,
            (spot_id, spot_id)
        )

        origin = cur.fetchone()

        if not origin:
            return {"alternatives": []}

        (
            origin_spot_id,
            origin_area_cd,
            origin_content_id,
            origin_name,
            origin_category,
            origin_description,
            origin_mapx,
            origin_mapy
        ) = origin

        # 2. 후보군 조회
        # 같은 카테고리 우선 + 여유/보통 우선.
        # 좌표가 있으면 가까운 순으로 정렬하고,
        # 좌표가 없는 경우에도 추천 자체는 동작하도록 처리.
        origin_x = float(origin_mapx) if origin_mapx is not None else None
        origin_y = float(origin_mapy) if origin_mapy is not None else None

        distance_order = """
            CASE
                WHEN %s IS NULL OR %s IS NULL
                     OR t.mapx IS NULL OR t.mapy IS NULL
                THEN 999999
                ELSE
                    POWER(CAST(t.mapx AS DOUBLE PRECISION) - %s, 2)
                    +
                    POWER(CAST(t.mapy AS DOUBLE PRECISION) - %s, 2)
            END
        """

        cur.execute(
            f"""
            SELECT
                CASE
                    WHEN l.source = 'actual'
                    THEN l.area_cd
                    ELSE l.content_id
                END AS spot_id,
                l.area_cd,
                l.content_id,
                {name_expr} AS name,
                {category_expr} AS category,
                t.image_url,
                {description_expr} AS description,
                {address_expr} AS address,
                t.mapx,
                t.mapy,
                l.congestion_level,
                l.source
            FROM latest_congestion l
            JOIN tour_spots t
                ON l.content_id = t.content_id
            LEFT JOIN seoul_spots s
                ON l.area_cd = s.area_cd
            WHERE
                (
                    CASE
                        WHEN l.source = 'actual'
                        THEN l.area_cd
                        ELSE l.content_id
                    END
                ) != %s
                AND l.congestion_level IN ('여유', '보통')
            ORDER BY
                CASE
                    WHEN {category_expr} = %s THEN 0
                    ELSE 1
                END,
                {distance_order},
                name
            LIMIT 40
            """,
            (
                spot_id,
                origin_category,
                origin_x,
                origin_y,
                origin_x,
                origin_y
            )
        )

        rows = cur.fetchall()

        if not rows:
            return {"alternatives": []}

        candidates = []

        for row in rows:
            candidates.append({
                "spot_id": row[0],
                "area_cd": row[1],
                "content_id": row[2],
                "name": row[3],
                "category": row[4],
                "image_url": row[5],
                "description": row[6],
                "address": row[7],
                "mapx": float(row[8]) if row[8] is not None else None,
                "mapy": float(row[9]) if row[9] is not None else None,
                "congestion_level": row[10],
                "congestion_source": row[11]
            })

        api_key = os.getenv("OPENAI_API_KEY")

        # OpenAI 키가 없으면 DB 추천 상위 4개
        if not api_key:
            return {"alternatives": candidates[:4]}

        candidate_text = "\n".join([
            (
                f"ID: {c['spot_id']} | "
                f"Name: {c['name']} | "
                f"Category: {c['category']} | "
                f"Description: {(c['description'] or '')[:120]}"
            )
            for c in candidates
        ])

        origin_desc = origin_description or ""

        if lang == "en":
            prompt = f"""
You are a Seoul travel recommendation assistant.

Target:
Name: {origin_name}
Category: {origin_category}
Description: {origin_desc[:200]}

Candidate List:
{candidate_text}

Choose exactly 4 destinations that are most similar
in theme, atmosphere, and travel purpose.

Rules:
1. Use ONLY IDs from Candidate List.
2. Prefer similar categories and experiences.
3. Candidates are already filtered to relatively low congestion.
4. Return ONLY 4 IDs separated by commas.
"""
        else:
            prompt = f"""
너는 서울 관광지 대안 추천 도우미다.

기존 관광지:
이름: {origin_name}
카테고리: {origin_category}
설명: {origin_desc[:200]}

후보 목록:
{candidate_text}

선택 기준:
1. 후보 목록의 ID만 사용한다.
2. 기존 관광지와 테마, 분위기, 방문 목적이 비슷한 곳을 우선한다.
3. 후보는 이미 여유/보통 혼잡도 위주로 필터링되어 있다.
4. 정확히 4개의 ID만 쉼표로 구분해 출력한다.
"""

        try:
            client = OpenAI(api_key=api_key)

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": prompt
                    }
                ]
            )

            ai_reply = (
                response
                .choices[0]
                .message
                .content
                or ""
            )

            selected_ids = [
                value.strip()
                for value in ai_reply.split(",")
                if value.strip()
            ]

        except Exception as ai_error:
            # AI 호출이 실패해도 대안 관광지 기능 자체는 계속 동작
            print(f"⚠️ AI 추천 실패, DB 추천으로 대체: {ai_error}")
            selected_ids = []

        candidate_map = {
            candidate["spot_id"]: candidate
            for candidate in candidates
        }

        alternatives = []

        for selected_id in selected_ids:
            if selected_id in candidate_map:
                alternatives.append(candidate_map[selected_id])

            if len(alternatives) == 4:
                break

        # AI 결과 부족/실패 시 DB 추천으로 보충
        if len(alternatives) < 4:
            existing_ids = {
                item["spot_id"]
                for item in alternatives
            }

            for candidate in candidates:
                if candidate["spot_id"] in existing_ids:
                    continue

                alternatives.append(candidate)

                if len(alternatives) == 4:
                    break

        return {"alternatives": alternatives}

    except Exception as e:
        print(f"🚨 대안 관광지 추천 에러: {e}")
        return {"alternatives": []}

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