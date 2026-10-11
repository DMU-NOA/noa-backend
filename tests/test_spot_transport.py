from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.api.endpoints import spot_transport, spots

KST = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 10, 11, 15, 0, tzinfo=KST)


class Cursor:
    def __init__(self, road=None, park=(), subway=(), bus=()):
        self.road = road
        self.park = list(park)
        self.subway = list(subway)
        self.bus = list(bus)
        self.queries = []
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute(self, sql, params): self.queries.append((sql,params))
    def fetchone(self): return self.road
    def fetchall(self):
        # Nearby transit uses 2 queries, road/parking uses 1-2 queries.
        if len(self.queries) == 1:
            return self.subway
        return self.park if "citydata_parking" in self.queries[-1][0] else self.bus


class Connection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.closed = False
    def cursor(self): return self.cursor_obj
    def close(self): self.closed = True


def test_road_and_parking_read_pipeline_tables(monkeypatch):
    cursor = Cursor(
        road=(24.2, "서행", datetime(2026,10,11,14,45,tzinfo=KST),
              "POI001", 0.0, True, "경복궁·서촌"),
        park=[("주차장 A", 7, 40, 1000, 350.3,
               datetime(2026,10,11,14,45,tzinfo=KST))],
    )
    conn = Connection(cursor)
    monkeypatch.setattr(spot_transport, "get_db", lambda: conn)
    traffic, parking = spot_transport.load_recent_road_parking("123", "POI001", (127.0,37.5), NOW)
    assert traffic["speed"] == 24.2
    assert traffic["source"] == "citydata_db"
    assert parking[0]["cur"] == 7
    assert parking[0]["distance_m"] == 350
    assert "citydata_road_traffic" in cursor.queries[0][0]
    assert "citydata_parking" in cursor.queries[1][0]
    assert "observed_at >= %s" in cursor.queries[0][0]
    assert cursor.queries[1][1][-1] == 2000
    assert cursor.queries[0][1][:2] == ("123", "123")
    assert "near.area_cd" in cursor.queries[0][0]
    assert "ST_DWithin" in cursor.queries[1][0]
    assert "p.area_cd = %s" not in cursor.queries[1][0]
    assert conn.closed


def test_unmapped_spot_still_queries_nearby_regions_and_parking(monkeypatch):
    cursor = Cursor(
        road=(19.5, "원활", datetime(2026,10,11,14,45,tzinfo=KST),
              "POI014", 240.7, False, "인근 관광 지역"),
        park=[("다른 지역에서 수집한 주차장", 8, 36, None, 450,
               datetime(2026,10,11,14,40,tzinfo=KST))],
    )
    conn = Connection(cursor)
    monkeypatch.setattr(spot_transport, "get_db", lambda: conn)
    road, lots = spot_transport.load_recent_road_parking("12345", None, (127.0,37.5), NOW)
    assert road["source_area_cd"] == "POI014"
    assert road["nearby"] is True
    assert road["distance_m"] == 241
    assert road["source_area_name"] == "인근 관광 지역"
    assert lots[0]["cur"] == 8
    assert cursor.queries[0][1][2:4] == (None, None)
    assert "n.distance_m <= %s" in cursor.queries[0][0]
    assert conn.closed


def test_no_parking_query_without_tourist_coordinates(monkeypatch):
    conn = Connection(Cursor(road=None))
    monkeypatch.setattr(spot_transport, "get_db", lambda: conn)
    assert spot_transport.load_recent_road_parking("123", "POI001", None, NOW) == (None, [])
    assert len(conn.cursor_obj.queries) == 1


def test_transit_is_monthly_aggregate_not_live(monkeypatch):
    cursor = Cursor(subway=[
        ("경복궁역", 270, date(2026,8,1), 15000.0, 13000.0),
        ("안국역", 670, None, None, None),
    ], bus=[("경복궁 정류장", 120, date(2026,8,1), 1200.0, 900.0)])
    conn = Connection(cursor)
    monkeypatch.setattr(spot_transport, "get_db", lambda: conn)
    result = spot_transport.load_nearby_transit("123", NOW)
    assert result["subway"][0]["ridership"]["month"] == "2026-08"
    assert result["subway"][0]["ridership"]["board_monthly"] == 15000
    assert result["subway"][1]["ridership"] is None
    assert result["bus"][0]["ridership"]["kind"] == "monthly_hour_total"
    assert "station_key" in cursor.queries[0][0]
    assert "n.distance_m <= 1000" in cursor.queries[0][0]
    assert "n.distance_m <= 500" in cursor.queries[1][0]
    assert conn.closed


def test_detail_combines_transport_weather_festivals_without_citydata(monkeypatch):
    weather = {"temp": 22, "source": "citydata_db"}
    nearby = {"subway": [{"name": "A"}], "bus": [], "hour": 15}
    monkeypatch.setattr(spots, "_spot_festivals_and_area",
                        lambda spot_id, today=None: (None, [{"name":"축제"}], (127,37.5)))
    monkeypatch.setattr(spots, "load_weather_from_db",
                        lambda spot_id, area_cd, lang="ko": weather)
    monkeypatch.setattr(spots, "load_nearby_transit", lambda spot_id: nearby)
    monkeypatch.setattr(spots, "load_recent_road_parking",
                        lambda spot_id, area_cd, coords: (None, []))
    result = spots.get_spot_additional_info("123")
    assert result["transit"] == nearby
    assert result["events"][0]["name"] == "축제"
    assert result["weather"] == weather
    assert result["traffic"] is None
