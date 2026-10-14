from fastapi import APIRouter, HTTPException
from datetime import date, datetime, timedelta
from math import asin, cos, radians, sin, sqrt
from zoneinfo import ZoneInfo
import re
from app.scripts.db import get_db
from app.api.endpoints.spot_weather import load_weather_from_db, live_weather_from_payload, resolve_citydata_area
from app.api.endpoints.spot_transport import load_nearby_transit, load_recent_road_parking
from app.api.endpoints.hourly_forecast import get_hourly_forecast
import os
import requests
from openai import OpenAI

router = APIRouter()

# 관광지를 기본으로 조회한다. 예전 미검증 predicted 값은 표시하지 않는다.
# DB 자체가 준비되지 않은 경우는 숨기지 않고 서버 오류로 알려준다.
SPOT_QUERY = """
SELECT
  COALESCE(m.area_cd, t.content_id) AS spot_id,
  m.area_cd, t.content_id,
  CASE WHEN %s = 'en'
    THEN COALESCE(NULLIF(s.name_en, ''), NULLIF(t.name_en, ''), s.name, t.name)
    ELSE COALESCE(s.name, t.name) END AS name,
  CASE WHEN %s = 'en'
    THEN COALESCE(s.category_en, s.category, t.category)
    ELSE COALESCE(s.category, t.category) END AS category,
  REPLACE(
    COALESCE(NULLIF(TRIM(t.image_url), ''), NULLIF(TRIM(t.image_url2), '')),
    'http://tong.visitkorea.or.kr/',
    'https://tong.visitkorea.or.kr/'
  ) AS image_url,
  CASE WHEN %s = 'en'
    THEN COALESCE(NULLIF(t.description_en, ''), NULLIF(t.description, ''), 'No description available.')
    ELSE COALESCE(NULLIF(t.description, ''), '상세 소개 정보가 없습니다.') END AS description,
  CASE WHEN %s = 'en'
    THEN COALESCE(NULLIF(t.address_en, ''), t.address)
    ELSE t.address END AS address,
  t.mapx, t.mapy,
  COALESCE(a.congestion_level, pr.congestion_level, '데이터 없음') AS congestion_level,
  COALESCE(a.source, pr.source) AS congestion_source,
  COALESCE(a.updated_at, pr.updated_at) AS updated_at,
  COALESCE(pr.prediction_verified, false) AS prediction_verified,
  pr.prediction_method,
  pr.reference_distance_m
FROM tour_spots t
LEFT JOIN spot_mapping m ON m.content_id = t.content_id
LEFT JOIN seoul_spots s ON s.area_cd = m.area_cd
LEFT JOIN latest_congestion a
  ON a.content_id = t.content_id AND a.source = 'actual'
LEFT JOIN latest_congestion pr
  ON pr.content_id = t.content_id AND pr.source = 'predicted'
  AND a.content_id IS NULL
"""


def _serialize(row):
    return {
        "spot_id": str(row[0]), "area_cd": row[1], "content_id": row[2],
        "name": row[3], "category": row[4], "image_url": row[5],
        "description": row[6], "address": row[7],
        "mapx": float(row[8]) if row[8] is not None else None,
        "mapy": float(row[9]) if row[9] is not None else None,
        "congestion_level": row[10], "congestion_source": row[11],
        "updated_at": row[12].isoformat() if row[12] else None,
        "prediction_verified": bool(row[13]) if row[11] == "predicted" else None,
        "prediction_method": row[14] if row[11] == "predicted" else None,
        "reference_distance_m": row[15] if row[11] == "predicted" else None,
    }


def _load_spots(lang="ko", keyword=None, spot_id=None):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            sql = SPOT_QUERY
            params = [lang] * 4
            if spot_id is None:
                # 화면 카드에는 사진과 실질적인 소개가 모두 있는 관광지만 노출한다.
                # 관광지 원본 레코드는 삭제하지 않아 이후 상세 수집으로 복구 가능하다.
                sql += """
                WHERE COALESCE(
                  NULLIF(TRIM(t.image_url), ''),
                  NULLIF(TRIM(t.image_url2), '')
                ) IS NOT NULL
                AND NULLIF(TRIM(t.description), '') IS NOT NULL
                AND TRIM(t.description) NOT IN (
                  '상세 소개 정보가 없습니다.', 'No description available.'
                )
                """
                if keyword is not None:
                    sql += """
                    AND (COALESCE(s.name, '') ILIKE %s
                      OR COALESCE(s.name_en, '') ILIKE %s
                      OR COALESCE(t.name, '') ILIKE %s
                      OR COALESCE(t.name_en, '') ILIKE %s
                      OR COALESCE(t.description, '') ILIKE %s
                      OR COALESCE(t.category, '') ILIKE %s)
                    """
                    params += [f"%{keyword}%"] * 6
            else:
                sql += " WHERE (m.area_cd = %s OR t.content_id = %s)"
                params += [spot_id, spot_id]
            sql += " ORDER BY name"
            try:
                cur.execute(sql, params)
            except Exception as exc:
                # 아직 migration 하지 않은 완전 빈 DB에서도 프론트 목록은 [].
                # 연결 오류/권한 오류 등 다른 문제는 숨기지 않는다.
                if getattr(exc, "pgcode", None) == "42P01":
                    conn.rollback()
                    return []
                raise
            return [_serialize(row) for row in cur.fetchall()]
    finally:
        conn.close()


@router.get("/observed-areas")
def get_observed_areas(lang: str = "ko"):
    """TourAPI 매핑 및 사진/상세 소개가 없어도 모든 실측 지역을 제공."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT a.area_cd,
                       CASE WHEN %s = 'en'
                         THEN COALESCE(NULLIF(s.name_en, ''), s.name)
                         ELSE s.name END,
                       s.category, a.congestion_level, a.updated_at,
                       a.content_id
                FROM latest_congestion a
                JOIN seoul_spots s ON s.area_cd = a.area_cd
                WHERE a.source = 'actual'
                ORDER BY s.name
                """, (lang,)
            )
            data = [
                {"area_cd": code, "name": name, "category": category,
                 "congestion_level": level, "congestion_source": "actual",
                 "updated_at": updated.isoformat() if updated else None,
                 "content_id": content}
                for code, name, category, level, updated, content in cur.fetchall()
            ]
            return {"count": len(data), "data": data}
    finally:
        conn.close()


@router.get("/spots")
def get_all_spots(lang: str = "ko"):
    rows = _load_spots(lang=lang)
    return {"count": len(rows), "data": rows}


@router.get("/spots/search")
def search_spots(keyword: str, lang: str = "ko"):
    return {"results": _load_spots(lang=lang, keyword=keyword), "recommendations": []}


@router.get("/spots/{spot_id}")
def get_spot_detail(spot_id: str, lang: str = "ko"):
    rows = _load_spots(lang=lang, spot_id=spot_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Spot not found")
    return rows[0]


@router.get("/spots/{spot_id}/signals")
def get_spot_signals(spot_id: str):
    """수집된 주변 관측 신호의 최신 상태. 직접 혼잡도/ML 결과가 아니다."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT content_id FROM tour_spots WHERE content_id = %s
                   UNION SELECT content_id FROM spot_mapping WHERE area_cd = %s
                   LIMIT 1""", (spot_id, spot_id)
            )
            found = cur.fetchone()
            if not found:
                raise HTTPException(status_code=404, detail="Spot not found")
            cid = found[0]
            cur.execute(
                """SELECT target_type, COUNT(*), MIN(distance_m)
                   FROM place_nearby WHERE content_id = %s
                   GROUP BY target_type ORDER BY target_type""", (cid,)
            )
            nearby = [
                {"type": a, "count": n, "nearest_m": round(float(d), 1)}
                for a, n, d in cur.fetchall()
            ]
            cur.execute(
                """SELECT o.visitor_count, o.observed_at, n.distance_m
                   FROM place_nearby n
                   JOIN LATERAL (
                     SELECT visitor_count, observed_at FROM sdot_observation
                     WHERE sensor_code::text = n.target_id
                     ORDER BY observed_at DESC LIMIT 1
                   ) o ON TRUE
                   WHERE n.content_id = %s AND n.target_type = 'sdot_sensor'
                   ORDER BY n.distance_m LIMIT 5""", (cid,)
            )
            sensors = [
                {"visitor_count": v, "observed_at": t.isoformat(),
                 "distance_m": round(float(d), 1)}
                for v, t, d in cur.fetchall()
            ]
            cur.execute(
                """SELECT h.hub_rank, h.base_ym, h.hub_tats_nm
                   FROM kto_place_match m
                   JOIN kto_hub_place h ON h.hub_tats_cd = m.tats_cd
                   WHERE m.content_id = %s
                   ORDER BY h.base_ym DESC, h.hub_rank LIMIT 1""", (cid,)
            )
            row = cur.fetchone()
            popularity = (
                {"rank": row[0], "month": row[1].isoformat(), "name": row[2]}
                if row else None
            )
            return {"content_id": cid, "nearby": nearby,
                    "sdot_observations": sensors, "kto_hub": popularity,
                    "notice": "관측 참고정보이며 장소의 실제 혼잡도나 ML 예측이 아닙니다."}
    finally:
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
    """Serve fresh official CityData or validated area-level ML predictions from DB."""
    return get_hourly_forecast(spot_id, lang=lang)


# Date windows and coordinates for every festival use the tourist's local date.
FESTIVAL_RADIUS_M = 3000
FESTIVAL_DAYS_AHEAD = 30


def _festival_status(start: date, end: date, today: date):
    """Ended and too-distant-future events are not suitable for the detail page."""
    if start > end or end < today or start > today + timedelta(days=FESTIVAL_DAYS_AHEAD):
        return None
    return "ongoing" if start <= today else "upcoming"


def _event_period_dates(value: str):
    """Parse dated Seoul CityData events. Unverifiable date strings are excluded."""
    matches = re.findall(
        r"(?<!\d)(\d{4})[^\d]{0,5}(\d{1,2})[^\d]{0,5}(\d{1,2})(?!\d)",
        str(value or ""),
    )
    try:
        dates = [date(int(y), int(m), int(d)) for y, m, d in matches]
    except ValueError:
        return None
    if not dates:
        return None
    if len(dates) == 1 and any(mark in str(value) for mark in ("~", "～", "부터", "까지")):
        # Ambiguous intervals (missing end year) cannot be reliably validated.
        return None
    return (dates[0], dates[-1])


def _distance_meters(lon1, lat1, lon2, lat2):
    """Haversine distance for Seoul CityData events with coordinates."""
    x1, y1, x2, y2 = map(float, (lon1, lat1, lon2, lat2))
    if not (-180 <= x1 <= 180 and -180 <= x2 <= 180
            and -90 <= y1 <= 90 and -90 <= y2 <= 90):
        raise ValueError("Invalid event coordinates")
    d_lat, d_lon = radians(y2 - y1), radians(x2 - x1)
    a = sin(d_lat / 2) ** 2 + cos(radians(y1)) * cos(radians(y2)) * sin(d_lon / 2) ** 2
    return 2 * 6371000 * asin(min(1.0, sqrt(a)))


def _seoul_events_in_radius(items, coords, today):
    """Only geolocated, dated CityData events within the same 3 km radius."""
    if coords is None:
        return []
    lon, lat = coords
    result = []
    for event in items:
        if not isinstance(event, dict) or not event.get("EVENT_NM"):
            continue
        period = _event_period_dates(event.get("EVENT_PERIOD", ""))
        if not period:
            continue
        start, end = period
        status = _festival_status(start, end, today)
        if status is None:
            continue
        try:
            distance = _distance_meters(lon, lat, event["EVENT_X"], event["EVENT_Y"])
        except (KeyError, ValueError, TypeError):
            continue
        if distance > FESTIVAL_RADIUS_M:
            continue
        result.append({
            "name": str(event["EVENT_NM"]),
            "period": str(event.get("EVENT_PERIOD") or ""),
            "place": str(event.get("EVENT_PLACE") or ""),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "status": status,
            "source": "seoul_citydata",
            "distance_m": round(distance),
        })
    return result


def _spot_festivals_and_area(spot_id: str, today: date | None = None):
    """Resolve area + spot coordinates, then fetch only dated 3 km TourAPI events."""
    today = today or datetime.now(ZoneInfo("Asia/Seoul")).date()
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(
                    (SELECT s.area_cd FROM seoul_spots s WHERE s.area_cd = %s),
                    (SELECT m.area_cd FROM spot_mapping m WHERE m.content_id = %s)
                ), place.mapx, place.mapy
                FROM (SELECT 1) AS anchor
                LEFT JOIN LATERAL (
                    SELECT t.mapx, t.mapy
                    FROM tour_spots t
                    LEFT JOIN spot_mapping m ON m.content_id = t.content_id
                    WHERE t.content_id = %s OR m.area_cd = %s
                    LIMIT 1
                ) place ON TRUE
                """,
                (spot_id, spot_id, spot_id, spot_id),
            )
            area_cd, longitude, latitude = cur.fetchone()
            cur.execute(
                """
                SELECT f.title, f.event_start_date, f.event_end_date,
                       CONCAT_WS(' ', f.addr1, f.addr2) AS venue,
                       ST_Distance(
                           f.location,
                           ST_SetSRID(ST_MakePoint(t.mapx::double precision,
                                                   t.mapy::double precision), 4326)::geography
                       ) AS distance_m
                FROM tour_spots t
                LEFT JOIN spot_mapping m ON m.content_id = t.content_id
                JOIN tour_festival f
                  ON f.lang = 'ko'
                  AND f.location IS NOT NULL
                  AND f.event_start_date IS NOT NULL
                  AND f.event_end_date IS NOT NULL
                  AND f.event_start_date <= f.event_end_date
                  AND f.event_end_date >= %s
                  AND f.event_start_date <= %s
                  AND f.collected_at >= %s
                  AND t.mapx IS NOT NULL AND t.mapy IS NOT NULL
                  AND ST_DWithin(
                      f.location,
                      ST_SetSRID(ST_MakePoint(t.mapx::double precision,
                                              t.mapy::double precision), 4326)::geography,
                      3000
                  )
                WHERE t.content_id = %s OR m.area_cd = %s
                ORDER BY CASE WHEN f.event_start_date <= %s THEN 0 ELSE 1 END,
                         f.event_start_date, distance_m, f.title
                LIMIT 12
                """,
                (today, today + timedelta(days=FESTIVAL_DAYS_AHEAD),
                 datetime.combine(today - timedelta(days=7), datetime.min.time(), ZoneInfo("Asia/Seoul")),
                 spot_id, spot_id, today),
            )
            festivals = []
            for name, start, end, venue, distance in cur.fetchall():
                status = _festival_status(start, end, today)
                if status is None:
                    continue
                festivals.append({
                    "name": name,
                    "period": f"{start:%Y.%m.%d} ~ {end:%Y.%m.%d}",
                    "place": venue or "",
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "status": status,
                    "source": "tourapi",
                    "distance_m": round(float(distance)),
                })
            coords = (
                (float(longitude), float(latitude))
                if longitude is not None and latitude is not None else None
            )
            return area_cd, festivals, coords
    finally:
        conn.close()


@router.get("/spots/{spot_id}/additional-info")
def get_spot_additional_info(spot_id: str, lang: str = "ko"):
    # A TourAPI tourist spot may have festivals even if it has no CityData area.
    # The old endpoint returned an entirely empty response in that situation.
    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    area_cd, festivals, coords = _spot_festivals_and_area(spot_id, today=today)
    # Every tourist spot can use a recent observation from a nearby CityData area.
    # A true mapped area still prefers a fresh live API response if available.
    db_weather = load_weather_from_db(spot_id, area_cd, lang=lang)
    nearby_transit = load_nearby_transit(spot_id)
    # Transport values are read from the pipeline's timestamped DB tables only.
    traffic, parking_lots = load_recent_road_parking(spot_id, area_cd, coords)
    empty = {
        "weather": db_weather, "traffic": traffic,
        "parking_lots": parking_lots, "events": festivals,
        "transit": nearby_transit,
    }
    try:
        live_area_cd = resolve_citydata_area(spot_id, area_cd)
        if not live_area_cd:
            return empty
        api_key = os.getenv("SEOUL_API_KEY")
        if not api_key:
            return empty

        api_type = "citydata_eng" if lang == "en" else "citydata"
        url = f"http://openapi.seoul.go.kr:8088/{api_key}/json/{api_type}/1/5/{live_area_cd}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        citydata = response.json().get("CITYDATA")
        if not isinstance(citydata, dict):
            return empty

        weather = live_weather_from_payload(citydata, lang=lang) or db_weather
        if weather and weather.get('source') == 'citydata_live_api' and not area_cd:
            weather = {**weather, 'nearby': True}

        seoul_events = citydata.get("CULTURALEVENTINFO") or []
        if isinstance(seoul_events, dict):
            seoul_events = [seoul_events]
        events = list(festivals)
        seen = {(e["name"].strip().casefold(), e["place"].strip().casefold()) for e in events}
        for new_event in _seoul_events_in_radius(seoul_events, coords, today):
            key = (new_event["name"].strip().casefold(), new_event["place"].strip().casefold())
            if key not in seen:
                events.append(new_event)
                seen.add(key)
        events.sort(key=lambda e: (e["status"] != "ongoing",
                                   e["start_date"], e["distance_m"]))

        return {
            "weather": weather, "traffic": traffic,
            "parking_lots": parking_lots, "events": events,
            "transit": nearby_transit,
        }
    except Exception as exc:
        print(f"부가정보 CityData 조회 실패 (관광지 {spot_id}): {type(exc).__name__}")
        # External API failure must not hide already-loaded festival data.
        return empty
