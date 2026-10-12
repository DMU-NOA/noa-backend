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


ROAD_RADIUS_M = 1000


def load_recent_road_parking(spot_id, area_cd=None, coords=None, now=None):
    """Read stored CityData observations matched by geography, never collect data.

    Road values from a neighboring CityData region are *regional reference
    readings*, not traffic measured at the tourist spot. Parking is selected
    solely by its actual coordinate distance (2 km), irrespective of which
    CityData region happened to include it.
    """
    now = now or datetime.now(KST)
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH targets AS (
                    SELECT content_id FROM tour_spots WHERE content_id = %s
                    UNION
                    SELECT content_id FROM spot_mapping WHERE area_cd = %s
                ), candidates AS (
                    SELECT %s::text AS area_cd, 0.0::double precision AS distance_m,
                           TRUE AS direct
                    WHERE %s::text IS NOT NULL
                    UNION ALL
                    SELECT n.target_id, n.distance_m, FALSE
                    FROM place_nearby n
                    JOIN targets t ON t.content_id = n.content_id
                    WHERE n.target_type = 'citydata_area'
                      AND n.distance_m <= %s
                ), nearby AS (
                    SELECT area_cd, MIN(distance_m) AS distance_m,
                           BOOL_OR(direct) AS direct
                    FROM candidates
                    GROUP BY area_cd
                )
                SELECT road.avg_speed, road.road_msg, road.observed_at,
                       near.area_cd, near.distance_m, near.direct, area.area_nm
                FROM nearby near
                JOIN citydata_area area ON area.area_cd = near.area_cd
                JOIN LATERAL (
                    SELECT r.avg_speed, r.road_msg, r.observed_at
                    FROM citydata_road_traffic r
                    WHERE r.area_cd = near.area_cd
                      AND r.observed_at >= %s AND r.observed_at <= %s
                      AND r.avg_speed BETWEEN 0 AND 200
                    ORDER BY r.observed_at DESC LIMIT 1
                ) road ON TRUE
                ORDER BY NOT near.direct, near.distance_m, road.observed_at DESC
                LIMIT 1
                """,
                (spot_id, spot_id, area_cd, area_cd, ROAD_RADIUS_M,
                 now - LIVE_MAX_AGE, now + timedelta(minutes=5)),
            )
            observed = cur.fetchone()
            traffic = None
            if observed:
                speed, message, stamp, source_area, distance, direct, source_name = observed
                traffic = {
                    "speed": float(speed),
                    "msg": message or "",
                    "observed_at": _serialize_time(stamp),
                    "source": "citydata_db",
                    "source_area_cd": source_area,
                    "source_area_name": source_name,
                    "nearby": not bool(direct),
                    # Distance is to the observed CityData region boundary,
                    # not to the roadway or its particular speed sensors.
                    "distance_m": round(float(distance)) if not direct else None,
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
                               ST_Distance(
                                   p.location,
                                   ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                               ) AS distance_m,
                               p.observed_at
                        FROM citydata_parking p
                        WHERE p.observed_at >= %s AND p.observed_at <= %s
                          AND ST_DWithin(
                              p.location,
                              ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                              %s
                          )
                        ORDER BY p.parking_key, p.observed_at DESC, p.collected_at DESC
                    ) latest
                    ORDER BY distance_m, parking_name
                    LIMIT 10
                    """,
                    (lon, lat, now - LIVE_MAX_AGE, now + timedelta(minutes=5),
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
