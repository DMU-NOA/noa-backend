"""Read already-processed transport tables from the NOA shared PostgreSQL DB.

Collection, validation, and historical snapshot ingestion belong exclusively
to the data-pipelines project. This module only filters/serializes DB records.
Monthly subway/bus counts remain historical statistics, not live data.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.scripts.db import get_db

KST = ZoneInfo("Asia/Seoul")
LIVE_MAX_AGE = timedelta(minutes=90)
PARKING_RADIUS_M = 2000


def _serialize_time(stamp):
    if stamp is None:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=KST)
    return stamp.astimezone(KST).isoformat()


def load_recent_road_parking(area_cd, coords=None, now=None):
    """Read timestamped road and parking observations already stored by pipeline.

    Direct mapping only. Never label a nearby-region road speed as the tourist
    spot's live traffic, and never display expired parking counts as live.
    """
    if not area_cd:
        return None, []
    now = now or datetime.now(KST)
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT avg_speed, road_msg, observed_at
                FROM citydata_road_traffic
                WHERE area_cd = %s
                  AND observed_at >= %s AND observed_at <= %s
                  AND avg_speed BETWEEN 0 AND 200
                ORDER BY observed_at DESC LIMIT 1
                """,
                (area_cd, now - LIVE_MAX_AGE, now + timedelta(minutes=5)),
            )
            observed = cur.fetchone()
            traffic = None
            if observed:
                speed, message, stamp = observed
                traffic = {
                    "speed": float(speed),
                    "msg": message or "",
                    "observed_at": _serialize_time(stamp),
                    "source": "citydata_db",
                    "source_area_cd": area_cd,
                }

            parking = []
            if coords is not None:
                lon, lat = coords
                cur.execute(
                    """
                    SELECT parking_name, available_count, capacity,
                           base_fee, distance_m, observed_at
                    FROM (
                        SELECT DISTINCT ON (p.parking_key)
                               p.parking_key, p.parking_name,
                               p.available_count, p.capacity, p.base_fee,
                               ST_Distance(p.location,
                                   ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                               ) AS distance_m,
                               p.observed_at
                        FROM citydata_parking p
                        WHERE p.area_cd = %s
                          AND p.observed_at >= %s AND p.observed_at <= %s
                          AND ST_DWithin(
                              p.location,
                              ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                              %s
                          )
                        ORDER BY p.parking_key, p.observed_at DESC
                    ) latest
                    ORDER BY distance_m, parking_name LIMIT 10
                    """,
                    (lon, lat, area_cd,
                     now - LIVE_MAX_AGE, now + timedelta(minutes=5),
                     lon, lat, PARKING_RADIUS_M),
                )
                parking = [
                    {
                        "name": name,
                        "cur": available,
                        "max": capacity,
                        "fee": fee,
                        "distance_m": round(float(distance)),
                        "observed_at": _serialize_time(stamp),
                        "source": "citydata_db",
                    }
                    for name, available, capacity, fee, distance, stamp in cur.fetchall()
                ]
            return traffic, parking
    finally:
        conn.close()


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
