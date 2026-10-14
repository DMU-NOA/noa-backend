"""Read already-collected official or independently validated hourly area forecasts.

Only data-pipelines fetches/learns/writes. The FastAPI API never calls
Seoul CityData directly in the hourly forecast endpoint.
Area forecasts for nearby tourist spots are labelled regional references.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from app.scripts.db import get_db

KST = ZoneInfo("Asia/Seoul")
MAX_AGE = timedelta(hours=2)


def _stamp(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=KST)
    return value.astimezone(KST).isoformat()


def _formatted(value, lang):
    if value.tzinfo is None:
        value = value.replace(tzinfo=KST)
    local = value.astimezone(KST)
    return local.strftime("%m.%d %H시" if lang == "ko" else "%m/%d %H:00")


def get_hourly_forecast(spot_id, lang="ko", now=None):
    now = now or datetime.now(KST)
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH candidates AS (
                    SELECT s.area_cd, 0.0::float AS distance_m, TRUE AS direct
                    FROM seoul_spots s WHERE s.area_cd = %s
                    UNION ALL
                    SELECT m.area_cd, 0.0::float, TRUE
                    FROM spot_mapping m WHERE m.content_id = %s
                    UNION ALL
                    SELECT n.target_id, n.distance_m, FALSE
                    FROM place_nearby n
                    WHERE n.content_id = %s
                      AND n.target_type = 'citydata_area'
                      AND n.distance_m <= 1000
                )
                SELECT c.area_cd, c.distance_m, c.direct
                FROM candidates c
                ORDER BY NOT c.direct, c.distance_m, c.area_cd
                LIMIT 1
                """,
                (spot_id, spot_id, spot_id),
            )
            selected = cur.fetchone()
            if not selected:
                return {"forecast": [], "source": None}
            area, distance, direct = selected
            cur.execute(
                """
                SELECT forecast_at, congestion_level, issued_at,
                       validation_balanced_accuracy,
                       validation_baseline_accuracy
                FROM area_hourly_forecast
                WHERE area_cd = %s
                  AND issued_at BETWEEN %s AND %s
                  AND forecast_at > %s AND forecast_at <= %s
                  AND model_version = 'area_hourly_v2'
                ORDER BY forecast_at LIMIT 12
                """,
                (area, now - MAX_AGE, now + timedelta(minutes=5),
                 now, now + timedelta(hours=12)),
            )
            predictions = cur.fetchall()
            if predictions:
                return {
                    "source": "validated_ml_v2",
                    "regional_reference": not direct,
                    "source_area_cd": area,
                    "reference_distance_m": round(float(distance)) if not direct else None,
                    "observed_at": _stamp(predictions[0][2]),
                    "forecast": [
                        {
                            "time": _formatted(at, lang), "forecast_at": _stamp(at),
                            "level": level, "population": None,
                            "source": "validated_ml_v2",
                            "balanced_accuracy": score,
                            "baseline_balanced_accuracy": baseline,
                        }
                        for at, level, _issued, score, baseline in predictions
                    ],
                }

            # The CityData official forecast was collected by the pipeline,
            # never fetched directly by this API request.
            cur.execute(
                """
                SELECT DISTINCT ON (fcst_time)
                       fcst_time, congest_lvl, ppltn_max, ppltn_time
                FROM citydata_forecast
                WHERE area_cd = %s
                  AND ppltn_time BETWEEN %s AND %s
                  AND fcst_time > %s AND fcst_time <= %s
                  AND congest_lvl IN ('여유','보통','약간 붐빔','붐빔')
                ORDER BY fcst_time, ppltn_time DESC
                LIMIT 12
                """,
                (area, now - MAX_AGE, now + timedelta(minutes=5),
                 now, now + timedelta(hours=12)),
            )
            official = cur.fetchall()
            historical = False
            if not official:
                # Demo fallback: show the last *issued* official forecast cycle
                # as historical reference only. Never pretend expired hours are future.
                cur.execute(
                    """
                    SELECT DISTINCT ON (fcst_time)
                           fcst_time, congest_lvl, ppltn_max, ppltn_time
                    FROM citydata_forecast
                    WHERE area_cd = %s
                      AND ppltn_time = (
                        SELECT MAX(ppltn_time) FROM citydata_forecast
                        WHERE area_cd = %s AND ppltn_time <= %s
                      )
                      AND congest_lvl IN ('여유','보통','약간 붐빔','붐빔')
                    ORDER BY fcst_time, ppltn_time DESC
                    LIMIT 12
                    """,
                    (area, area, now + timedelta(minutes=5)),
                )
                official = cur.fetchall()
                historical = bool(official)
            return {
                "historical": historical,
                "source": "seoul_citydata_official" if official else None,
                "regional_reference": not direct,
                "source_area_cd": area,
                "reference_distance_m": round(float(distance)) if not direct else None,
                "observed_at": _stamp(official[0][3]) if official else None,
                "forecast": [
                    {
                        "time": _formatted(at, lang),
                        "forecast_at": _stamp(at), "level": level,
                        "population": int(max_people) if max_people is not None else None,
                        "source": "seoul_citydata_official",
                    }
                    for at, level, max_people, _issued in official
                ],
            }
    finally:
        conn.close()
