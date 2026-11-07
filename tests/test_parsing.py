from custom_components.stellplatz_wetter.api import distance_km, parse_forecast, parse_nominatim_search, parse_reverse, parse_search
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
    assert parse_search({}) == []
    places = parse_search({"results": [{"name": "Wien", "latitude": 48.2, "longitude": 16.37, "admin1": "Wien", "country": "Österreich"}]})
    assert places[0].name == "Wien, Österreich"
    assert parse_reverse({"address": {"village": "Mamming", "county": "Dingolfing-Landau"}}) == "Mamming"
    assert parse_reverse({}) is None


def test_distance():
    assert 290 < distance_km(48.14, 11.58, 45.68, 13.39) < 320


def test_search_results_limited_unique():
    items = [{"name": "Neustadt", "latitude": 49 + i, "longitude": 11, "admin1": "Bayern", "country": "Deutschland"} for i in range(5)]
    items.insert(1, {"name": "Neustadt", "latitude": 49.001, "longitude": 11.001, "admin1": "Bayern", "country": "Deutschland"})
    places = parse_search({"results": items})
    assert len(places) == 3
    assert len({p.name for p in places}) == 3  # gleiche Namen unterscheidbar
    assert places[0].name == "Neustadt, Bayern, Deutschland"


def test_nominatim_postcode():
    payload = [{"lat": "48.63", "lon": "12.49", "display_name": "84130, Dingolfing, Bayern, Deutschland",
                "address": {"postcode": "84130", "town": "Dingolfing", "state": "Bayern", "country": "Deutschland"}}]
    assert parse_nominatim_search(payload, "84130")[0].name == "84130 Dingolfing, Bayern, Deutschland"
    no_town = [{"lat": "48.6", "lon": "12.5", "display_name": "84130, Bayern, Deutschland", "address": {"postcode": "84130"}}]
    assert parse_nominatim_search(no_town, "84130")[0].name == "84130, Bayern, Deutschland"
    assert parse_nominatim_search({"error": "x"}) == []


def test_postcode_regex():
    from custom_components.stellplatz_wetter.api import POSTCODE_RE
    assert POSTCODE_RE.match("84130")["code"] == "84130"
    m = POSTCODE_RE.match(" 6020, at ")
    assert m["code"] == "6020" and m["cc"] == "at"
    assert POSTCODE_RE.match("84130 DE")["cc"] == "DE"
    assert POSTCODE_RE.match("Grado") is None
    assert POSTCODE_RE.match("123") is None
