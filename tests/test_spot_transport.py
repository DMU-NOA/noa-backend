from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.api.endpoints import spot_transport, spots

KST = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 10, 11, 15, 0, tzinfo=KST)


def test_live_road_requires_recent_timestamp():
    payload = {"AREA_CD": "POI001", "ROAD_TRAFFIC_STTS": {
        "ROAD_TRAFFIC_TIME": "2026-10-11 14:40",
        "AVG_ROAD_DATA": {"ROAD_TRAFFIC_SPD": "22.3", "ROAD_MSG": "서행"}
    }}
    road, parking = spot_transport.live_transport_from_citydata(payload, now=NOW)
    assert road["speed"] == 22.3
    assert road["observed_at"] == "2026-10-11T14:40:00+09:00"
    assert parking == []
    payload["ROAD_TRAFFIC_STTS"]["ROAD_TRAFFIC_TIME"] = "2026-10-11 08:00"
    road, _ = spot_transport.live_transport_from_citydata(payload, now=NOW)
    assert road is None
    payload["ROAD_TRAFFIC_STTS"].pop("ROAD_TRAFFIC_TIME")
    road, _ = spot_transport.live_transport_from_citydata(payload, now=NOW)
    assert road is None


def test_only_nearby_fresh_live_parking_is_published():
    payload = {"PRK_STTS": [
        {"PRK_NM": "가까운 주차장", "LNG": "127.001", "LAT": "37.501",
         "CUR_PRK_YN": "Y", "CUR_PRK_TIME": "2026-10-11 14:40",
         "CUR_PRK_CNT": "3", "CPCTY": "50", "RATES": "1000"},
        {"PRK_NM": "이미 종료된 관측", "LNG": "127.001", "LAT": "37.501",
         "CUR_PRK_YN": "Y", "CUR_PRK_TIME": "2026-10-11 12:00",
         "CUR_PRK_CNT": "6", "CPCTY": "50"},
        {"PRK_NM": "너무 먼 곳", "LNG": "127.1", "LAT": "37.5",
         "CUR_PRK_YN": "Y", "CUR_PRK_TIME": "2026-10-11 14:40",
         "CUR_PRK_CNT": "6", "CPCTY": "50"},
        {"PRK_NM": "실시간 미제공", "LNG": "127.001", "LAT": "37.501",
         "CUR_PRK_YN": "N", "CUR_PRK_TIME": "2026-10-11 14:40",
         "CUR_PRK_CNT": "6", "CPCTY": "50"}
    ]}
    _, lots = spot_transport.live_transport_from_citydata(payload, coords=(127, 37.5), now=NOW)
    assert [p["name"] for p in lots] == ["가까운 주차장"]
    assert lots[0]["cur"] == 3
    assert lots[0]["max"] == 50
    assert lots[0]["distance_m"] < 2000
    _, lots = spot_transport.live_transport_from_citydata(payload, coords=None, now=NOW)
    assert lots == []


class FakeCursor:
    def __init__(self):
        self.calls = []
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute(self, sql, params): self.calls.append((sql,params))
    def fetchall(self):
        if len(self.calls) == 1:
            return [("경복궁역", 270, date(2026, 8, 1), 15000.0, 13000.0),
                    ("안국역", 670, None, None, None)]
        return [("경복궁 버스정류장", 120, date(2026, 8, 1), 1200.0, 900.0)]


class FakeConnection:
    def __init__(self):
        self.cur = FakeCursor()
        self.closed = False
    def cursor(self): return self.cur
    def close(self): self.closed = True


def test_transit_is_geolocated_monthly_aggregate_not_realtime(monkeypatch):
    con = FakeConnection()
    monkeypatch.setattr(spot_transport, "get_db", lambda: con)
    value = spot_transport.load_nearby_transit("123", now=NOW)
    assert [x["name"] for x in value["subway"]] == ["경복궁역", "안국역"]
    assert value["subway"][0]["distance_m"] == 270
    assert value["subway"][0]["ridership"] == {
        "month": "2026-08", "hour": 15, "board_monthly": 15000,
        "alight_monthly": 13000, "kind": "monthly_hour_total",
    }
    assert value["subway"][1]["ridership"] is None
    assert value["bus"][0]["ridership"]["month"] == "2026-08"
    assert "station_key" in con.cur.calls[0][0]
    assert "n.distance_m <= 1000" in con.cur.calls[0][0]
    assert "n.distance_m <= 500" in con.cur.calls[1][0]
    assert con.cur.calls[0][1] == ("123", "123", 15)
    assert con.closed


def test_detail_additional_info_keeps_festivals_and_weather_when_no_live_traffic(monkeypatch):
    expected_weather = {"temp": 22, "source": "citydata_db"}
    nearby = {"subway": [{"name": "A"}], "bus": [], "hour": 15}
    monkeypatch.setattr(spots, "_spot_festivals_and_area",
                        lambda spot_id, today=None: (None, [{"name":"축제"}], (127,37.5)))
    monkeypatch.setattr(spots, "load_weather_from_db",
                        lambda spot_id, area_cd, lang="ko": expected_weather)
    monkeypatch.setattr(spots, "load_nearby_transit", lambda spot_id: nearby)
    result = spots.get_spot_additional_info("123")
    assert result["transit"] == nearby
    assert result["events"][0]["name"] == "축제"
    assert result["weather"] == expected_weather
    assert result["traffic"] is None
