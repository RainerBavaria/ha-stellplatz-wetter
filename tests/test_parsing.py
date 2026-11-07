from custom_components.stellplatz_wetter.api import distance_km, parse_forecast, parse_reverse, parse_search
from custom_components.stellplatz_wetter.weather import condition_for

from .payloads import forecast


def test_condition():
    assert condition_for(0, 1) == "sunny"
    assert condition_for(0, 0) == "clear-night"
    assert condition_for(1, 0) == "clear-night"
    assert condition_for(82) == "pouring"
    assert condition_for(None) is None
    assert condition_for(5) is None


def test_parse_forecast_times_are_utc():
    data = parse_forecast(forecast())
    assert data.hourly[0]["time"].isoformat() == "2026-11-06T23:00:00+00:00"
    assert data.daily[0]["sunrise"].isoformat() == "2026-11-07T05:10:00+00:00"
    assert data.current["temperature_2m"] == 6.8


def test_parse_search_and_reverse():
    assert parse_search({}) is None
    place = parse_search({"results": [{"name": "Wien", "latitude": 48.2, "longitude": 16.37, "admin1": "Wien", "country": "Österreich"}]})
    assert place.name == "Wien, Österreich"
    assert parse_reverse({"address": {"village": "Mamming", "county": "Dingolfing-Landau"}}) == "Mamming"
    assert parse_reverse({}) is None


def test_distance():
    assert 290 < distance_km(48.14, 11.58, 45.68, 13.39) < 320
