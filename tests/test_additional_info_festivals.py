from datetime import date
from types import SimpleNamespace

from app.api.endpoints import spots


class _FakeCursor:
    def __init__(self, area_cd="POI001", festivals=()):
        self.area_cd = area_cd
        self.festivals = festivals
        self.query_index = 0
        self.sql = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params):
        self.sql.append((sql, params))
        self.query_index += 1

    def fetchone(self):
        assert self.query_index == 1
        return (self.area_cd,)

    def fetchall(self):
        assert self.query_index == 2
        return list(self.festivals)


class _FakeConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


def test_tour_festivals_are_mapped_to_existing_event_contract(monkeypatch):
    cursor = _FakeCursor(
        festivals=[("가을 음악 축제", date(2026, 10, 12), date(2026, 10, 14),
                    "서울 종로구", 845.7)]
    )
    conn = _FakeConnection(cursor)
    monkeypatch.setattr(spots, "get_db", lambda: conn)

    area, events = spots._spot_festivals_and_area("POI001")
    assert area == "POI001"
    assert events == [{
        "name": "가을 음악 축제",
        "period": "2026.10.12 ~ 2026.10.14",
        "place": "서울 종로구",
        "source": "tourapi",
        "distance_m": 846.0,
    }]
    assert conn.closed
    assert "ST_DWithin" in cursor.sql[1][0]
    assert "f.event_end_date >=" in cursor.sql[1][0]


def test_tourist_without_citydata_keeps_db_festivals(monkeypatch):
    festival = {"name": "행사", "period": "2026.10.11 ~ 2026.10.12",
                "place": "서울", "source": "tourapi", "distance_m": 20}
    monkeypatch.setattr(spots, "_spot_festivals_and_area",
                        lambda spot_id: (None, [festival]))
    monkeypatch.setattr(spots.requests, "get", lambda *args, **kwargs:
                        (_ for _ in ()).throw(AssertionError("CityData should not be called")))
    assert spots.get_spot_additional_info("12345") == {
        "weather": None, "traffic": None, "parking_lots": [], "events": [festival],
    }


def test_citydata_error_does_not_erase_festival_results(monkeypatch):
    festival = {"name": "행사", "period": "2026.10.11 ~ 2026.10.12",
                "place": "서울", "source": "tourapi"}
    monkeypatch.setattr(spots, "_spot_festivals_and_area",
                        lambda spot_id: ("POI001", [festival]))
    monkeypatch.setenv("SEOUL_API_KEY", "dummy")
    def fail(*args, **kwargs):
        raise RuntimeError("API temporarily unavailable")
    monkeypatch.setattr(spots.requests, "get", fail)
    result = spots.get_spot_additional_info("POI001")
    assert result["events"] == [festival]
    assert result["weather"] is None


def test_citydata_events_are_combined_without_losing_weather(monkeypatch):
    festival = {"name": "주변 축제", "period": "2026.10.12 ~ 2026.10.14",
                "place": "서울", "source": "tourapi"}
    monkeypatch.setattr(spots, "_spot_festivals_and_area",
                        lambda spot_id: ("POI001", [festival]))
    monkeypatch.setenv("SEOUL_API_KEY", "dummy")
    class _Response:
        def raise_for_status(self): pass
        def json(self):
            return {"CITYDATA": {
                "WEATHER_STTS": [{"TEMP": "20", "FCST24HOURS": []}],
                "CULTURALEVENTINFO": [{"EVENT_NM": "서울 행사",
                                      "EVENT_PERIOD": "2026.10.11",
                                      "EVENT_PLACE": "서울광장"}],
            }}
    monkeypatch.setattr(spots.requests, "get", lambda *args, **kwargs: _Response())
    result = spots.get_spot_additional_info("POI001")
    assert result["weather"]["temp"] == "20"
    assert len(result["events"]) == 2
    assert {ev["source"] for ev in result["events"]} == {"tourapi", "seoul_citydata"}
