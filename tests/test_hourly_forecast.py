from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.api.endpoints import hourly_forecast

NOW = datetime(2026, 10, 11, 16, 30, tzinfo=ZoneInfo("Asia/Seoul"))


class Cursor:
    def __init__(self, chosen, predictions=(), official=()):
        self.chosen = chosen
        self.predictions = predictions
        self.official = official
        self.calls = []
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute(self, sql, params): self.calls.append((sql, params))
    def fetchone(self): return self.chosen
    def fetchall(self):
        return list(self.predictions if len(self.calls) == 2 else self.official)


class DB:
    def __init__(self, c): self.c = c
    def cursor(self): return self.c
    def close(self): pass


def test_only_validated_published_hourly_model_is_returned(monkeypatch):
    c = Cursor(("POI005", 0, True), predictions=[
        (NOW + timedelta(hours=1), "보통", NOW - timedelta(minutes=7),
         .62, .49)
    ])
    monkeypatch.setattr(hourly_forecast, "get_db", lambda: DB(c))
    result = hourly_forecast.get_hourly_forecast("123", now=NOW)
    assert result["source"] == "validated_ml_v2"
    assert result["regional_reference"] is False
    assert result["forecast"][0]["population"] is None
    assert result["forecast"][0]["balanced_accuracy"] == .62
    assert c.calls[1][1][1] == NOW - timedelta(hours=2)
    assert "area_hourly_forecast" in c.calls[1][0]


def test_citydata_fallback_is_official_not_our_model(monkeypatch):
    c = Cursor(("POI021", 650, False), official=[
        (NOW + timedelta(hours=2), "약간 붐빔", 13000, NOW - timedelta(minutes=20))
    ])
    monkeypatch.setattr(hourly_forecast, "get_db", lambda: DB(c))
    result = hourly_forecast.get_hourly_forecast("123", now=NOW)
    assert result["source"] == "seoul_citydata_official"
    assert result["regional_reference"] is True
    assert result["source_area_cd"] == "POI021"
    assert result["forecast"][0]["population"] == 13000
    assert "citydata_forecast" in c.calls[-1][0]


def test_unlinked_spot_returns_no_fabricated_forecast(monkeypatch):
    c = Cursor(None)
    monkeypatch.setattr(hourly_forecast, "get_db", lambda: DB(c))
    result = hourly_forecast.get_hourly_forecast("123", now=NOW)
    assert result["forecast"] == []
    assert len(c.calls) == 1
