from datetime import date
import pytest
from app.api.endpoints import spots


@pytest.fixture(autouse=True)
def mock_weather_db(monkeypatch):
    # Existing festival tests must not access a real CityData weather DB.
    monkeypatch.setattr(spots, "load_weather_from_db",
                        lambda spot_id, area_cd, lang="ko": None)



class _FakeCursor:
    def __init__(self, area_cd="POI001", festivals=(), coordinates=(127.0, 37.5)):
        self.area_cd = area_cd
        self.festivals = festivals
        self.coordinates = coordinates
        self.query_index = 0
        self.sql = []
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute(self, sql, params):
        self.sql.append((sql, params))
        self.query_index += 1
    def fetchone(self):
        return (self.area_cd, *self.coordinates)
    def fetchall(self):
        return list(self.festivals)


class _FakeConnection:
    def __init__(self, cur):
        self.cur = cur
        self.closed = False
    def cursor(self): return self.cur
    def close(self): self.closed = True


def test_query_rejects_ended_and_far_tour_festivals(monkeypatch):
    fake = _FakeCursor(festivals=[
        ("가까운 행사", date(2026, 10, 9), date(2026, 10, 11), "서울", 845.7),
        ("곧 시작", date(2026, 10, 20), date(2026, 10, 22), "서울", 2010.0),
    ])
    conn = _FakeConnection(fake)
    monkeypatch.setattr(spots, "get_db", lambda: conn)
    area, events, coords = spots._spot_festivals_and_area("POI001", date(2026,10,11))
    assert area == "POI001" and coords == (127.0, 37.5)
    assert [e["status"] for e in events] == ["ongoing", "upcoming"]
    assert [e["distance_m"] for e in events] == [846, 2010]
    sql, params = fake.sql[1]
    assert "ST_DWithin" in sql
    assert "f.event_end_date >= %s" in sql
    assert "f.event_start_date <= %s" in sql
    assert "f.event_start_date <= f.event_end_date" in sql
    assert params[:2] == (date(2026, 10, 11), date(2026, 11, 10))
    assert "f.collected_at >= %s" in sql
    assert conn.closed


def test_festival_status_date_boundaries():
    today = date(2026,10,11)
    assert spots._festival_status(date(2026,10,9),date(2026,10,9),today) is None
    assert spots._festival_status(date(2026,10,9),date(2026,10,11),today) == "ongoing"
    assert spots._festival_status(date(2026,10,20),date(2026,10,21),today) == "upcoming"
    assert spots._festival_status(date(2026,11,10),date(2026,11,12),today) == "upcoming"
    assert spots._festival_status(date(2026,11,11),date(2026,11,12),today) is None
    assert spots._festival_status(date(2026,10,20),date(2026,10,19),today) is None


def test_citydata_date_and_radius_filter():
    today = date(2026,10,11)
    items = [
        {"EVENT_NM":"종료행사", "EVENT_PERIOD":"2026.10.07 ~ 2026.10.09",
         "EVENT_PLACE":"서울", "EVENT_X":"127.001", "EVENT_Y":"37.501"},
        {"EVENT_NM":"진행중", "EVENT_PERIOD":"2026-10-09~2026-10-12",
         "EVENT_PLACE":"서울", "EVENT_X":"127.001", "EVENT_Y":"37.501"},
        {"EVENT_NM":"예정", "EVENT_PERIOD":"2026/10/20 - 2026/10/25",
         "EVENT_PLACE":"서울", "EVENT_X":"127.002", "EVENT_Y":"37.502"},
        {"EVENT_NM":"너무먼곳", "EVENT_PERIOD":"2026.10.20",
         "EVENT_PLACE":"서울", "EVENT_X":"127.10", "EVENT_Y":"37.50"},
        {"EVENT_NM":"위치없음", "EVENT_PERIOD":"2026.10.20", "EVENT_PLACE":"서울"},
        {"EVENT_NM":"날짜없음", "EVENT_PERIOD":"행사 예정", "EVENT_X":"127.001", "EVENT_Y":"37.501"},
        {"EVENT_NM":"한달뒤", "EVENT_PERIOD":"2026.11.15", "EVENT_X":"127.001", "EVENT_Y":"37.501"},
    ]
    result = spots._seoul_events_in_radius(items, (127.0,37.5),today)
    assert [e["name"] for e in result] == ["진행중","예정"]
    assert [e["status"] for e in result] == ["ongoing","upcoming"]


def test_citydata_api_failure_does_not_hide_tourapi_events(monkeypatch):
    ev = {"name": "가까운 행사","period":"2026.10.11", "place":"서울",
          "status":"ongoing","start_date":"2026-10-11","end_date":"2026-10-11",
          "source":"tourapi","distance_m":140}
    monkeypatch.setattr(spots, "_spot_festivals_and_area",
                        lambda spot_id, today=None: ("POI001", [ev], (127.0, 37.5)))
    monkeypatch.setenv("SEOUL_API_KEY", "dummy")
    def fail(*a,**k): raise RuntimeError("network error")
    monkeypatch.setattr(spots.requests, "get",fail)
    data = spots.get_spot_additional_info("POI001")
    assert data["events"] == [ev]
    assert data["weather"] is None


def test_tourist_without_citydata_uses_tourapi_events(monkeypatch):
    ev = {"name":"축제","status":"upcoming","source":"tourapi"}
    monkeypatch.setattr(spots,"_spot_festivals_and_area",
                        lambda spot_id, today=None: (None,[ev],(127.0,37.5)))
    def fail(*a,**k): raise AssertionError("unexpected CityData call")
    monkeypatch.setattr(spots.requests,"get",fail)
    assert spots.get_spot_additional_info("123")["events"] == [ev]


def test_citydata_events_deduplicate_with_existing_tourapi(monkeypatch):
    ev = {"name": "행사", "period": "2026.10.11", "place":"서울",
          "status":"ongoing","start_date":"2026-10-11","end_date":"2026-10-11",
          "source":"tourapi","distance_m":200}
    monkeypatch.setattr(spots, "_spot_festivals_and_area",
                        lambda spot_id, today=None: ("POI001",[ev],(127.0,37.5)))
    monkeypatch.setattr(spots,"_seoul_events_in_radius",
                        lambda items, coords, today: [
                            dict(ev, source="seoul_citydata"),
                            dict(ev, name="또다른 행사", source="seoul_citydata")])
    monkeypatch.setenv("SEOUL_API_KEY", "dummy")
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"CITYDATA": {
                "WEATHER_STTS":[{"TEMP":"20"}],
                "CULTURALEVENTINFO":[{"EVENT_NM":"행사"}],
            }}
    monkeypatch.setattr(spots.requests,"get",lambda *a,**k: Response())
    monkeypatch.setattr(spots, "live_weather_from_payload",
                        lambda citydata, lang="ko": {"temp": "20"})
    result = spots.get_spot_additional_info("POI001")
    assert [e["name"] for e in result["events"]] == ["행사", "또다른 행사"]
    assert result["weather"]["temp"] == "20"
