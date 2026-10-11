"""Weather and PM2.5/PM10 for tourist spots from collected CityData observations.

Do not represent city-level or old weather as a spot's real-time measurements.
No direct-spot meteorological sensor is implied by a nearby area.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.scripts.db import get_db


KST = ZoneInfo("Asia/Seoul")
MAX_WEATHER_AGE = timedelta(hours=3)

# Korea AirKorea's published PM10/PM2.5 four-tier concentration ranges.
def particle_grade(value, *, fine: bool = False, lang: str = "ko"):
    if value is None:
        return None
    try:
        value = float(value)
    except (ValueError, TypeError):
        return None
    if value < 0:
        return None
    cutoffs = (15, 35, 75) if fine else (30, 80, 150)
    index = sum(value > bound for bound in cutoffs)
    return (("Good", "Moderate", "Bad", "Very bad")
            if lang == "en" else ("좋음", "보통", "나쁨", "매우 나쁨"))[index]


def _recent_time(value, now):
    """Return timezone-aware local time only for genuinely recent observations."""
    if not value:
        return None
    try:
        if isinstance(value, datetime):
            stamp = value
        else:
            stamp = datetime.fromisoformat(str(value).strip())
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=KST)
        stamp = stamp.astimezone(KST)
    except (ValueError, TypeError):
        return None
    age = now - stamp
    return stamp if -timedelta(minutes=5) <= age <= MAX_WEATHER_AGE else None


def _valid_forecasts(rows, now, lang):
    out = []
    for timestamp, temp, sky, rain_chance in rows:
        if not timestamp:
            continue
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=KST)
        timestamp = timestamp.astimezone(KST)
        if timestamp < now or timestamp > now + timedelta(hours=24):
            continue
        out.append({
            "time": timestamp.strftime("%m.%d %H시" if lang == "ko" else "%m/%d %H:00"),
            "temp": temp if temp is not None else "-",
            "sky": sky or "-",
            "rain_chance": rain_chance if rain_chance is not None else "-",
        })
    return out


def load_weather_from_db(spot_id, area_cd=None, *, lang="ko", now=None):
    """Select current weather from mapped region or nearest stored <=1km area.

    Weather is only displayed when observed in the last 3 hours.
    It returns None when no appropriately fresh, geographically linked observation exists.
    """
    now = now or datetime.now(KST)
    conn = get_db()
    try:
        with conn.cursor() as cur:
            # Resolve near-area IDs only for the selected tourist spot.
            # Directly mapped CityData regions take priority if fresh.
            cur.execute(
                """
                WITH candidates AS (
                    SELECT %s::text AS area_cd, -1.0::double precision AS distance_m
                    WHERE %s::text IS NOT NULL
                    UNION ALL
                    SELECT n.target_id, n.distance_m
                    FROM place_nearby n
                    LEFT JOIN spot_mapping m ON m.content_id = n.content_id
                    WHERE n.target_type = 'citydata_area'
                      AND n.distance_m <= 1000
                      AND (n.content_id = %s OR m.area_cd = %s)
                ), nearest AS (
                    SELECT DISTINCT ON (area_cd) area_cd, distance_m
                    FROM candidates
                    WHERE area_cd IS NOT NULL
                    ORDER BY area_cd, distance_m
                )
                SELECT w.area_cd, w.weather_time, w.temperature, w.humidity,
                       w.precipitation, w.precpt_type, w.pm10, w.pm25,
                       n.distance_m
                FROM nearest n
                JOIN LATERAL (
                    SELECT area_cd, weather_time, temperature, humidity,
                           precipitation, precpt_type, pm10, pm25
                    FROM citydata_weather
                    WHERE area_cd = n.area_cd AND weather_time >= %s
                      AND weather_time <= %s
                    ORDER BY weather_time DESC LIMIT 1
                ) w ON true
                ORDER BY (n.distance_m >= 0), n.distance_m, w.weather_time DESC
                LIMIT 1
                """,
                (area_cd, area_cd, spot_id, spot_id,
                 now - MAX_WEATHER_AGE, now + timedelta(minutes=5)),
            )
            data = cur.fetchone()
            if not data:
                return None
            (source_area, observed_at, temp, humidity, precipitation,
             precpt_type, pm10, pm25, distance) = data
            observed_at = _recent_time(observed_at, now)
            if observed_at is None:
                return None

            cur.execute(
                """
                SELECT fcst_time, temperature, sky_stts, rain_chance
                FROM citydata_weather_forecast
                WHERE area_cd = %s AND weather_time = %s
                  AND fcst_time >= %s AND fcst_time <= %s
                ORDER BY fcst_time LIMIT 30
                """,
                (source_area, observed_at, now, now + timedelta(hours=24)),
            )
            forecast = _valid_forecasts(cur.fetchall(), now, lang)

            return {
                "temp": temp,
                "humidity": humidity,
                "pm10_val": pm10,
                "pm25_val": pm25,
                "pm10": particle_grade(pm10, lang=lang),
                "pm25": particle_grade(pm25, fine=True, lang=lang),
                "msg": precpt_type if precpt_type and precpt_type != "-" else
                       (precipitation if precipitation and precipitation != "-" else None),
                "forecast24": forecast,
                "source": "citydata_db",
                "source_area_cd": source_area,
                "distance_m": round(float(distance)) if distance is not None and distance >= 0 else None,
                "observed_at": observed_at.isoformat(),
                "nearby": distance is not None and distance >= 0,
            }
    finally:
        conn.close()


def live_weather_from_payload(citydata, *, lang="ko", now=None):
    """Only prefer direct CityData API weather if its WEATHER_TIME is fresh."""
    now = now or datetime.now(KST)
    items = citydata.get("WEATHER_STTS") or []
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        return None
    w = items[0]
    observed_at = _recent_time(w.get("WEATHER_TIME"), now)
    if observed_at is None:
        return None

    raw_forecast = w.get("FCST24HOURS") or []
    if isinstance(raw_forecast, dict):
        raw_forecast = [raw_forecast]
    forecasts = []
    for f in raw_forecast if isinstance(raw_forecast, list) else []:
        try:
            stamp = datetime.strptime(str(f.get("FCST_DT")), "%Y%m%d%H%M").replace(tzinfo=KST)
        except (ValueError, TypeError, AttributeError):
            continue
        forecasts.append((stamp, f.get("TEMP"), f.get("SKY_STTS"), f.get("RAIN_CHANCE")))
    forecasts = _valid_forecasts(forecasts, now, lang)

    def _number(value):
        try:
            if value in ("", "-", None):
                return None
            return float(value)
        except (ValueError, TypeError):
            return None

    pm10 = _number(w.get("PM10"))
    pm25 = _number(w.get("PM25"))
    return {
        "temp": _number(w.get("TEMP")),
        "humidity": _number(w.get("HUMIDITY")),
        "pm10_val": pm10,
        "pm25_val": pm25,
        "pm10": w.get("PM10_INDEX") or particle_grade(pm10, lang=lang),
        "pm25": w.get("PM25_INDEX") or particle_grade(pm25, fine=True, lang=lang),
        "msg": w.get("PCP_MSG") if lang == "en" else w.get("WEATHER_MSG"),
        "forecast24": forecasts,
        "source": "citydata_live_api",
        "source_area_cd": citydata.get("AREA_CD"),
        "distance_m": None,
        "observed_at": observed_at.isoformat(),
        "nearby": False,
    }
