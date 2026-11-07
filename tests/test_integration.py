"""Ende-zu-Ende-Tests in einer echten Home-Assistant-Instanz (Netz gemockt)."""
from datetime import timedelta

import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.stellplatz_wetter.const import DOMAIN, FORECAST_URL, GEOCODING_URL, REVERSE_URL

from .payloads import forecast

NOW = "2026-11-07T09:21:00+00:00"
TRACKER = "device_tracker.womo_iphone"


@pytest.fixture(autouse=True)
def _custom(enable_custom_integrations):
    yield


@pytest.fixture
async def setup(hass, aioclient_mock, freezer):
    freezer.move_to(NOW)
    await hass.config.async_update(time_zone="Europe/Berlin", latitude=48.64, longitude=12.49, language="de")
    aioclient_mock.get(FORECAST_URL, json=forecast(gust_peak=45.0))
    aioclient_mock.get(REVERSE_URL, json={"address": {"town": "Grado", "county": "Gorizia"}})
    hass.states.async_set(TRACKER, "not_home", {"latitude": 45.678, "longitude": 13.395})

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is data_entry_flow.FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {
        "name": "Wohnwagen", "tracker": TRACKER, "location": {"latitude": 48.64, "longitude": 12.49},
    })
    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    return hass.config_entries.async_entries(DOMAIN)[0]


def forecast_calls(aioclient_mock):
    return [c for c in aioclient_mock.mock_calls if str(c[1]).startswith(FORECAST_URL)]


async def test_entities_and_current_weather(hass, setup, aioclient_mock):
    state = hass.states.get("weather.wohnwagen_wetter")
    assert state is not None, [s.entity_id for s in hass.states.async_all()]
    assert state.state == "partlycloudy"
    a = state.attributes
    assert a["temperature"] == 6.8 and a["humidity"] == 78 and a["pressure"] == 1022.3
    assert a["wind_speed"] == 7.2 and a["wind_bearing"] == 240 and a["wind_gust_speed"] == 15.1
    assert a["supported_features"] == 3
    url = forecast_calls(aioclient_mock)[0][1]
    assert url.query["latitude"] == "45.6780" and url.query["timeformat"] == "unixtime"

    assert hass.states.get("sensor.wohnwagen_ort").state == "Grado"
    assert hass.states.get("sensor.wohnwagen_ort").attributes["quelle"] == "tracker"
    assert hass.states.get("select.wohnwagen_standortquelle").state == "tracker"
    assert hass.states.get("binary_sensor.wohnwagen_markisenwarnung").state == "on"
    assert hass.states.get("binary_sensor.wohnwagen_markisenwarnung").attributes["max_boeen_kmh"] == 45.0
    assert hass.states.get("binary_sensor.wohnwagen_sturmwarnung").state == "off"
    assert hass.states.get("binary_sensor.wohnwagen_frostwarnung").state == "off"


async def test_forecast_service(hass, setup):
    for kind, expected_first in (("daily", "2026-11-06T23:00:00+00:00"), ("hourly", "2026-11-07T09:00:00+00:00")):
        res = await hass.services.async_call("weather", "get_forecasts", {"entity_id": "weather.wohnwagen_wetter", "type": kind},
                                             blocking=True, return_response=True)
        fc = res["weather.wohnwagen_wetter"]["forecast"]
        assert fc[0]["datetime"] == expected_first
        if kind == "daily":
            assert len(fc) == 7
            assert fc[0]["condition"] == "rainy" and fc[0]["temperature"] == 9 and fc[0]["templow"] == 2
            assert fc[0]["precipitation"] == 1.2 and fc[0]["precipitation_probability"] == 60
        else:
            assert len(fc) == 72
            assert fc[0]["temperature"] == 7.0
            night = [f for f in fc if f["is_daytime"] is False][0]
            assert night["condition"] == "cloudy"


async def test_tracker_move_refetches(hass, setup, aioclient_mock):
    before = len(forecast_calls(aioclient_mock))
    hass.states.async_set(TRACKER, "not_home", {"latitude": 45.679, "longitude": 13.396})  # ~100 m
    await hass.async_block_till_done()
    assert len(forecast_calls(aioclient_mock)) == before
    hass.states.async_set(TRACKER, "not_home", {"latitude": 46.05, "longitude": 14.5})  # Ljubljana
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_shift(hass, 15))
    await hass.async_block_till_done()
    calls = forecast_calls(aioclient_mock)
    assert len(calls) == before + 1
    assert calls[-1][1].query["latitude"] == "46.0500"


def dt_shift(hass, seconds):
    from homeassistant.util import dt as dt_util
    return dt_util.utcnow() + timedelta(seconds=seconds)


async def test_place_search_sets_manual_location(hass, setup, aioclient_mock):
    aioclient_mock.get(GEOCODING_URL, json={"results": [{"name": "Lignano Sabbiadoro", "latitude": 45.69, "longitude": 13.14,
                                                         "admin1": "Friaul-Julisch Venetien", "country": "Italien"}]})
    await hass.services.async_call("text", "set_value", {"entity_id": "text.wohnwagen_ortssuche", "value": "Lignano"}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get("select.wohnwagen_standortquelle").state == "manual"
    assert hass.states.get("sensor.wohnwagen_ort").state == "Lignano Sabbiadoro, Friaul-Julisch Venetien, Italien"
    assert forecast_calls(aioclient_mock)[-1][1].query["latitude"] == "45.6900"
    assert hass.states.get("text.wohnwagen_ortssuche").state == "Lignano"

    # zurück auf GPS
    await hass.services.async_call("select", "select_option", {"entity_id": "select.wohnwagen_standortquelle", "option": "tracker"}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.wohnwagen_ort").state == "Grado"


async def test_place_search_not_found(hass, setup, aioclient_mock):
    aioclient_mock.get(GEOCODING_URL, json={"generationtime_ms": 0.1})
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("text", "set_value", {"entity_id": "text.wohnwagen_ortssuche", "value": "Xyzzyqq"}, blocking=True)
    assert hass.states.get("select.wohnwagen_standortquelle").state == "tracker"


async def test_network_outage_keeps_last_data(hass, setup, aioclient_mock):
    aioclient_mock.clear_requests()
    aioclient_mock.get(FORECAST_URL, exc=TimeoutError())
    aioclient_mock.get(REVERSE_URL, json={"address": {"town": "Grado"}})
    entry = setup
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    state = hass.states.get("weather.wohnwagen_wetter")
    assert state.state == "partlycloudy"
    assert hass.states.get("sensor.wohnwagen_ort").attributes["daten_veraltet"] is True


async def test_tracker_unavailable_uses_last_known(hass, setup, aioclient_mock):
    hass.states.async_set(TRACKER, "unavailable", {})
    await setup.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.wohnwagen_ort").attributes["quelle"] == "tracker_last_known"
    assert forecast_calls(aioclient_mock)[-1][1].query["latitude"] == "45.6780"


async def test_options_flow_map_and_thresholds(hass, setup, aioclient_mock):
    entry = setup
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is data_entry_flow.FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(result["flow_id"], {
        "tracker": TRACKER, "location": {"latitude": 47.0, "longitude": 11.0}, "update_minutes": 30,
        "awning_gust_kmh": 50, "storm_gust_kmh": 75, "frost_temperature": 2,
    })
    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert hass.states.get("select.wohnwagen_standortquelle").state == "manual"
    assert forecast_calls(aioclient_mock)[-1][1].query["latitude"] == "47.0000"
    assert hass.states.get("binary_sensor.wohnwagen_markisenwarnung").state == "off"  # 45 < 50

    # nur Grenzwerte ändern -> Standortquelle bleibt
    await hass.services.async_call("select", "select_option", {"entity_id": "select.wohnwagen_standortquelle", "option": "tracker"}, blocking=True)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {
        "tracker": TRACKER, "location": {"latitude": 47.0, "longitude": 11.0}, "update_minutes": 30,
        "awning_gust_kmh": 40, "storm_gust_kmh": 75, "frost_temperature": 2,
    })
    await hass.async_block_till_done()
    assert hass.states.get("select.wohnwagen_standortquelle").state == "tracker"
    assert hass.states.get("binary_sensor.wohnwagen_markisenwarnung").state == "on"


async def test_without_tracker_and_frost(hass, aioclient_mock, freezer):
    freezer.move_to(NOW)
    await hass.config.async_update(time_zone="Europe/Berlin", language="de")
    aioclient_mock.get(FORECAST_URL, json=forecast(base_temp=-3.0))
    aioclient_mock.get(REVERSE_URL, json={"address": {"village": "Mamming"}})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    await hass.config_entries.flow.async_configure(result["flow_id"], {"name": "Test", "location": {"latitude": 48.65, "longitude": 12.6}})
    await hass.async_block_till_done()
    assert hass.states.get("select.test_standortquelle").attributes["options"] == ["manual"]
    assert hass.states.get("sensor.test_ort").state == "Mamming"
    assert hass.states.get("binary_sensor.test_frostwarnung").state == "on"


async def test_unload(hass, setup):
    assert await hass.config_entries.async_unload(setup.entry_id)
    await hass.async_block_till_done()


async def test_state_survives_reload(hass, setup, aioclient_mock):
    aioclient_mock.get(GEOCODING_URL, json={"results": [{"name": "Lignano", "latitude": 45.69, "longitude": 13.14, "country": "Italien"}]})
    await hass.services.async_call("text", "set_value", {"entity_id": "text.wohnwagen_ortssuche", "value": "Lignano"}, blocking=True)
    await hass.config_entries.async_reload(setup.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("select.wohnwagen_standortquelle").state == "manual"
    assert hass.states.get("sensor.wohnwagen_ort").state == "Lignano, Italien"
