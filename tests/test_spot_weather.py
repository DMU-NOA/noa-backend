from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.api.endpoints import spot_weather


KST = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 10, 11, 14, 0, tzinfo=KST)


def test_airkorea_pm_breakpoints():
    assert spot_weather.particle_grade(30) == "좋음"
    assert spot_weather.particle_grade(31) == "보통"
    assert spot_weather.particle_grade(80) == "보통"
    assert spot_weather.particle_grade(81) == "나쁨"
    assert spot_weather.particle_grade(151) == "매우 나쁨"
    assert spot_weather.particle_grade(15, fine=True) == "좋음"
    assert spot_weather.particle_grade(16, fine=True) == "보통"
    assert spot_weather.particle_grade(36, fine=True) == "나쁨"
    assert spot_weather.particle_grade(76, fine=True) == "매우 나쁨"
    assert spot_weather.particle_grade(None, fine=True) is None


def test_live_rejects_old_and_missing_observation_times():
    for time in ("2026-10-11 09:00", None, ""):
        record = {"WEATHER_STTS": [{"WEATHER_TIME": time, "TEMP": "21"}]}
        assert spot_weather.live_weather_from_payload(record, now=NOW) is None


def test_live_parses_pm_and_future_forecast():
    payload = {"WEATHER_STTS": [{
        "WEATHER_TIME": "2026-10-11 13:00", "TEMP": "22",
        "HUMIDITY": "50", "PM10": "83", "PM25": "18",
        "FCST24HOURS": [
            {"FCST_DT": "202610111500", "TEMP": "24", "SKY_STTS": "맑음", "RAIN_CHANCE": "10"},
            {"FCST_DT": "202610110900", "TEMP": "20"}
        ],
    }]}
    weather = spot_weather.live_weather_from_payload(payload, now=NOW)
    assert weather["pm10"] == "나쁨"
    assert weather["pm25"] == "보통"
    assert len(weather["forecast24"]) == 1
    assert weather["observed_at"] == "2026-10-11T13:00:00+09:00"


class Cursor:
    def __init__(self, current, forecast=()):
        self.current = current
        self.forecast = list(forecast)
        self.commands = []
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute(self, sql, params): self.commands.append((sql, params))
    def fetchone(self): return self.current
    def fetchall(self): return self.forecast


class Connection:
    def __init__(self, cur):
        self.cur = cur
        self.closed = False
    def cursor(self): return self.cur
    def close(self): self.closed = True


def test_db_nearby_returns_weather_and_origin(monkeypatch):
    stamp = NOW - timedelta(minutes=25)
    cur = Cursor(("POI024", stamp, 21.5, 56, "-", "없음", 35, 17, 470.0),
                 [(NOW+timedelta(hours=1), 20, "맑음", 10)])
    conn = Connection(cur)
    monkeypatch.setattr(spot_weather, "get_db", lambda: conn)
    value = spot_weather.load_weather_from_db("123456", now=NOW)
    assert value["temp"] == 21.5
    assert value["pm10"] == "보통"
    assert value["pm25"] == "보통"
    assert value["nearby"] is True
    assert value["distance_m"] == 470
    assert value["source_area_cd"] == "POI024"
    assert len(value["forecast24"]) == 1
    assert "n.distance_m <= 1000" in cur.commands[0][0]
    assert conn.closed


def test_db_no_fresh_observation_returns_none(monkeypatch):
    cur = Cursor(None)
    monkeypatch.setattr(spot_weather, "get_db", lambda: Connection(cur))
    assert spot_weather.load_weather_from_db("123456", now=NOW) is None
    assert len(cur.commands) == 1


def test_additional_info_for_unmapped_spot_uses_weather_without_citydata_api(monkeypatch):
    from app.api.endpoints import spots
    expected = {"temp": 22, "source": "citydata_db", "pm10": "보통"}
    monkeypatch.setattr(spots, "_spot_festivals_and_area",
                        lambda spot_id, today=None: (None, [], (127.0,37.5)))
    monkeypatch.setattr(spots, "load_weather_from_db",
                        lambda spot_id, area_cd, lang="ko": expected)
    monkeypatch.setattr(spots, "load_nearby_transit",
                        lambda spot_id: {"subway": [], "bus": [], "hour": 14})
    monkeypatch.setattr(spots, "load_recent_road_parking",
                        lambda spot_id, area_cd, coords: (None, []))
    def forbidden(*a, **k): raise AssertionError("should not call the Seoul API")
    monkeypatch.setattr(spots.requests, "get", forbidden)
    result = spots.get_spot_additional_info("12345")
    assert result["weather"] == expected
    assert result["events"] == []
