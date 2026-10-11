from app.api.endpoints.spots import _serialize


def test_spot_without_congestion_returns_missing_status():
    row = ("100", None, "100", "관광지", "자연·공원", None,
           "상세 소개 정보가 없습니다.", "서울", 127.0, 37.5,
           "데이터 없음", None, None)
    value = _serialize(row)
    assert value["congestion_level"] == "데이터 없음"
    assert value["congestion_source"] is None
    assert value["image_url"] is None


def test_spot_with_actual_keeps_source():
    row = ("POI001", "POI001", "100", "서울 명소", "공원",
           "url", "소개", "서울", 127.0, 37.5,
           "보통", "actual", None)
    value = _serialize(row)
    assert value["spot_id"] == "POI001"
    assert value["congestion_source"] == "actual"
