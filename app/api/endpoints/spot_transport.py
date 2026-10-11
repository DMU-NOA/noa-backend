"""Nearby transit statistics and fresh road/parking data for spot details.

Station/stop ridership is monthly aggregated historical data, NEVER live traffic.
Road/parking come only from directly mapped CityData locations and only
when the API supplies credible, recent observation timestamps.
"""
from datetime import datetime, timedelta
from math import asin, cos, radians, sin, sqrt
from zoneinfo import ZoneInfo

from app.scripts.db import get_db

KST = ZoneInfo("Asia/Seoul")
LIVE_MAX_AGE = timedelta(minutes=90)
PARKING_RADIUS_M = 2000


def _recent_time(value, now):
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
        if -timedelta(minutes=5) <= now - stamp <= LIVE_MAX_AGE:
            return stamp
    except (ValueError, TypeError):
        return None
    return None


def _number(value):
    try:
        if value is None or str(value).strip() in ("", "-"):
            return None
        return float(value)
    except (ValueError, TypeError):
        return None


def _nonnegative_int(value):
    v = _number(value)
    if v is None or v < 0 or not v.is_integer():
        return None
    return int(v)


def _straight_distance_m(from_coords, to_coords):
    lon1, lat1 = map(float, from_coords)
    lon2, lat2 = map(float, to_coords)
    if not (-180 <= lon1 <= 180 and -180 <= lon2 <= 180
            and -90 <= lat1 <= 90 and -90 <= lat2 <= 90):
        raise ValueError("invalid coordinates")
    dlon, dlat = radians(lon2-lon1), radians(lat2-lat1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    return 2 * 6371000 * asin(min(1, sqrt(a)))


def live_transport_from_citydata(citydata, coords=None, now=None):
    """Parse CityData road + parking only when each reading is current.

    Returns an independent (traffic, parking_lots) tuple, so one missing
    dataset does not prevent the other from being shown.
    """
    now = now or datetime.now(KST)
    road = citydata.get("ROAD_TRAFFIC_STTS") or {}
    if isinstance(road, list):
        road = road[0] if road and isinstance(road[0], dict) else {}
    traffic = None
    if isinstance(road, dict):
        avg = road.get("AVG_ROAD_DATA") or {}
        if isinstance(avg, list):
            avg = avg[0] if avg and isinstance(avg[0], dict) else {}
        if isinstance(avg, dict):
            stamp = _recent_time(
                road.get("ROAD_TRAFFIC_TIME") or avg.get("ROAD_TRAFFIC_TIME"), now
            )
            speed = _number(avg.get("ROAD_TRAFFIC_SPD", road.get("ROAD_TRAFFIC_SPD")))
            if stamp and speed is not None and 0 <= speed <= 200:
                traffic = {
                    "speed": speed,
                    "msg": avg.get("ROAD_MSG") or road.get("ROAD_MSG") or "",
                    "observed_at": stamp.isoformat(),
                    "source": "seoul_citydata",
                    "source_area_cd": citydata.get("AREA_CD"),
                }

    parking = citydata.get("PRK_STTS") or []
    if isinstance(parking, dict):
        parking = [parking]
    result = []
    if coords is None:
        return traffic, result
    for item in parking if isinstance(parking, list) else []:
        if not isinstance(item, dict) or not item.get("PRK_NM"):
            continue
        if str(item.get("CUR_PRK_YN") or "").upper() != "Y":
            continue
        stamp = _recent_time(item.get("CUR_PRK_TIME"), now)
        available = _nonnegative_int(item.get("CUR_PRK_CNT"))
        capacity = _nonnegative_int(item.get("CPCTY"))
        if stamp is None or available is None or capacity is None or available > capacity:
            continue
        try:
            distance = _straight_distance_m(
                coords, (item["LNG"], item["LAT"])
            )
        except (KeyError, ValueError, TypeError):
            continue
        if distance > PARKING_RADIUS_M:
            continue
        result.append({
            "name": str(item["PRK_NM"]),
            "cur": available,
            "max": capacity,
            "fee": _nonnegative_int(item.get("RATES")),
            "distance_m": round(distance),
            "observed_at": stamp.isoformat(),
            "source": "seoul_citydata",
        })
    result.sort(key=lambda p: (p["distance_m"], p["name"]))
    return traffic, result[:10]


def _monthly_pattern(month, board, alight, hour):
    """The collected source is a monthly SUM for a particular hour, not live."""
    return {
        "month": month.isoformat()[:7] if month else None,
        "hour": hour,
        "board_monthly": round(float(board)) if board is not None else None,
        "alight_monthly": round(float(alight)) if alight is not None else None,
        "kind": "monthly_hour_total",
    }


def load_nearby_transit(spot_id, now=None):
    """Nearby 1km subway and 500m bus locations, plus historical time-of-day counts."""
    now = now or datetime.now(KST)
    hour = now.astimezone(KST).hour
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH target AS (
                    SELECT content_id FROM tour_spots WHERE content_id = %s
                    UNION
                    SELECT content_id FROM spot_mapping WHERE area_cd = %s
                ),
                nearest AS (
                    SELECT DISTINCT ON (st.station_key)
                        st.station_key, st.station_nm, n.distance_m
                    FROM place_nearby n
                    JOIN target t ON t.content_id = n.content_id
                    JOIN subway_station st ON st.station_id = n.target_id
                    WHERE n.target_type = 'subway_station'
                      AND n.distance_m <= 1000
                    ORDER BY st.station_key, n.distance_m, st.station_id
                )
                SELECT near.station_nm, near.distance_m,
                       ride.use_month, ride.boarded, ride.alighted
                FROM nearest near
                LEFT JOIN LATERAL (
                    SELECT r.use_month,
                           SUM(r.get_on) AS boarded, SUM(r.get_off) AS alighted
                    FROM subway_ridership r
                    WHERE r.station_key = near.station_key AND r.hour = %s
                    GROUP BY r.use_month
                    ORDER BY r.use_month DESC LIMIT 1
                ) ride ON true
                ORDER BY near.distance_m, near.station_nm
                LIMIT 5
                """,
                (spot_id, spot_id, hour),
            )
            subway = [
                {
                    "name": name, "distance_m": round(float(distance)),
                    "ridership": _monthly_pattern(month, board, alight, hour)
                                   if month is not None else None,
                }
                for name, distance, month, board, alight in cur.fetchall()
            ]

            cur.execute(
                """
                WITH target AS (
                    SELECT content_id FROM tour_spots WHERE content_id = %s
                    UNION
                    SELECT content_id FROM spot_mapping WHERE area_cd = %s
                )
                SELECT st.stop_nm, n.distance_m,
                       ride.use_month, ride.get_on, ride.get_off
                FROM place_nearby n
                JOIN target t ON t.content_id = n.content_id
                JOIN bus_stop st ON st.stop_id = n.target_id
                LEFT JOIN LATERAL (
                    SELECT r.use_month, r.get_on, r.get_off
                    FROM bus_ridership r
                    WHERE r.stop_id = st.stop_id AND r.hour = %s
                    ORDER BY r.use_month DESC LIMIT 1
                ) ride ON true
                WHERE n.target_type = 'bus_stop' AND n.distance_m <= 500
                ORDER BY n.distance_m, st.stop_nm, st.stop_id
                LIMIT 5
                """,
                (spot_id, spot_id, hour),
            )
            buses = [
                {
                    "name": name, "distance_m": round(float(distance)),
                    "ridership": _monthly_pattern(month, board, alight, hour)
                                   if month is not None else None,
                }
                for name, distance, month, board, alight in cur.fetchall()
            ]
        return {"subway": subway, "bus": buses, "hour": hour}
    finally:
        conn.close()
