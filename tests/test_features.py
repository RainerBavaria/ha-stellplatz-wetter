"""Optionale Zusatzfunktionen."""
from datetime import timedelta

import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.stellplatz_wetter.const import DOMAIN, FORECAST_URL, REVERSE_URL
from custom_components.stellplatz_wetter.diagnostics import async_get_config_entry_diagnostics
from custom_components.stellplatz_wetter.warnings import DWD_URL, METEOALARM_URL

from .payloads import forecast

NOW = "2026-11-07T09:21:00+00:00"
TRACKER = "device_tracker.womo_iphone"
ALL = {"enable_solar": True, "enable_rain": True, "enable_thunder": True, "enable_sun": True,
       "enable_favorites": True, "enable_official_warnings": True}


@pytest.fixture(autouse=True)
def _custom(enable_custom_integrations):
    yield


def square(lon, lat, d=0.05):
    return {"type": "Polygon", "coordinates": [[[lon - d, lat - d], [lon + d, lat - d], [lon + d, lat + d], [lon - d, lat + d], [lon - d, lat - d]]]}


DWD = {"type": "FeatureCollection", "features": [
    {"geometry": square(13.395, 45.678), "properties": {"EVENT": "STURMBÖEN", "SEVERITY": "Moderate", "HEADLINE": "Amtliche WARNUNG vor STURMBÖEN",
                                                       "DESCRIPTION": "Es treten Sturmböen auf.", "ONSET": "2026-11-07T08:00:00Z", "EXPIRES": "2026-11-07T20:00:00Z"}},
    {"geometry": square(13.395, 45.678), "properties": {"EVENT": "FROST", "SEVERITY": "Minor", "HEADLINE": "Amtliche WARNUNG vor FROST",
                                                       "DESCRIPTION": "Frost.", "ONSET": "2026-11-07T20:00:00Z", "EXPIRES": "2026-11-08T08:00:00Z"}},
    {"geometry": square(14.0, 46.5), "properties": {"EVENT": "GEWITTER", "SEVERITY": "Severe", "HEADLINE": "woanders",
                                                    "DESCRIPTION": "", "ONSET": "2026-11-07T08:00:00Z", "EXPIRES": "2026-11-07T20:00:00Z"}},
    {"geometry": square(13.395, 45.678), "properties": {"EVENT": "GLÄTTE", "SEVERITY": "Minor", "HEADLINE": "abgelaufen",
                                                       "DESCRIPTION": "", "ONSET": "2026-11-06T08:00:00Z", "EXPIRES": "2026-11-07T08:00:00Z"}},
]}


async def setup_entry(hass, aioclient_mock, freezer, reverse=None, payload=None, features=ALL):
    freezer.move_to(NOW)
    await hass.config.async_update(time_zone="Europe/Berlin", latitude=48.64, longitude=12.49, language="de")
    aioclient_mock.get(FORECAST_URL, json=payload or forecast())
    aioclient_mock.get(REVERSE_URL, json=reverse or {"address": {"town": "Mamming", "state": "Bayern", "country_code": "de"}})
    aioclient_mock.get(DWD_URL, json=DWD)
    hass.states.async_set(TRACKER, "not_home", {"latitude": 45.678, "longitude": 13.395})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    await hass.config_entries.flow.async_configure(result["flow_id"], {"name": "Wohnwagen", "tracker": TRACKER,
                                                                       "location": {"latitude": 48.64, "longitude": 12.49}})
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    if features:
        await set_options(hass, entry, features)
    return entry


async def set_options(hass, entry, features, solar=None, remove=None):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    data = {"tracker": TRACKER, "location": {"latitude": 48.64, "longitude": 12.49}, "update_minutes": 30,
            "awning_gust_kmh": 38, "storm_gust_kmh": 75, "frost_temperature": 2, **features}
    if remove is not None:
        data["remove_favorites"] = remove
    result = await hass.config_entries.options.async_configure(result["flow_id"], data)
    if features.get("enable_solar"):
        assert result["type"] is data_entry_flow.FlowResultType.FORM and result["step_id"] == "solar"
        result = await hass.config_entries.options.async_configure(result["flow_id"], solar or {
            "pv_power_wp": 200, "pv_tilt": 0, "pv_azimuth": 0, "pv_efficiency": 75})
    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()


def states(hass, prefix):
    return sorted(s.entity_id for s in hass.states.async_all() if s.entity_id.split(".")[1].startswith(prefix))


async def test_default_has_no_extra_entities(hass, aioclient_mock, freezer):
    await setup_entry(hass, aioclient_mock, freezer, features=None)
    ids = states(hass, "wohnwagen_")
    assert ids == sorted([
        "binary_sensor.wohnwagen_frostwarnung", "binary_sensor.wohnwagen_markisenwarnung", "binary_sensor.wohnwagen_sturmwarnung",
        "select.wohnwagen_standortquelle", "select.wohnwagen_suchtreffer", "sensor.wohnwagen_ort",
        "text.wohnwagen_ortssuche", "weather.wohnwagen_wetter",
    ])
    # keine Zusatzabfragen
    assert not [c for c in aioclient_mock.mock_calls if str(c[1]).startswith(DWD_URL)]
    q = [c for c in aioclient_mock.mock_calls if str(c[1]).startswith(FORECAST_URL)][-1][1].query
    assert "minutely_15" not in q and "tilt" not in q


async def test_all_features(hass, aioclient_mock, freezer):
    await setup_entry(hass, aioclient_mock, freezer, payload=forecast(thunder_index=13))
    q = [c for c in aioclient_mock.mock_calls if str(c[1]).startswith(FORECAST_URL)][-1][1].query
    assert q["minutely_15"] == "precipitation" and q["tilt"] == "0" and "global_tilted_irradiance" in q["hourly"]

    # Solar: 10 Tagstunden x 300 W/m² = 3 kWh/m²; x 0,2 kWp x 75 % = 0,45 kWh
    assert float(hass.states.get("sensor.wohnwagen_solarprognose_heute").state) == 0.45
    assert float(hass.states.get("sensor.wohnwagen_solarprognose_morgen").state) == 0.45
    assert float(hass.states.get("sensor.wohnwagen_solarprognose_rest_heute").state) == 0.27  # ab 10:21 Ortszeit: 6 Stunden
    assert hass.states.get("sensor.wohnwagen_solarprognose_heute").attributes["unit_of_measurement"] == "kWh"

    # Regen: 0,4 mm im Viertel 10:45-11:00 Ortszeit -> in 24 Minuten
    assert hass.states.get("sensor.wohnwagen_regen_in").state == "24"
    rain = hass.states.get("binary_sensor.wohnwagen_regen_in_der_nachsten_stunde")
    assert rain.state == "on" and rain.attributes["menge_naechste_stunde_mm"] == 0.6

    thunder = hass.states.get("binary_sensor.wohnwagen_gewitterwarnung")
    assert thunder.state == "on" and thunder.attributes["erstes_gewitter"] == "2026-11-07T12:00:00+00:00"

    assert hass.states.get("sensor.wohnwagen_sonnenaufgang").state == "2026-11-08T05:10:00+00:00"
    assert hass.states.get("sensor.wohnwagen_sonnenuntergang").state == "2026-11-07T14:40:00+00:00"

    warn = hass.states.get("sensor.wohnwagen_amtliche_warnungen")
    assert warn.state == "2"  # anderer Ort und abgelaufene Warnung ausgefiltert
    assert warn.attributes["hoechste_stufe"] == 2 and warn.attributes["hoechste_stufe_text"] == "markant"
    assert warn.attributes["warnungen"][0]["ereignis"] == "Sturmböen" and warn.attributes["quelle"] == "DWD"
    dwd_q = [c for c in aioclient_mock.mock_calls if str(c[1]).startswith(DWD_URL)][-1][1].query
    assert dwd_q["typeName"] == "dwd:Warnungen_Gemeinden" and dwd_q["bbox"].startswith("13.393")


async def test_no_thunder_no_rain(hass, aioclient_mock, freezer):
    payload = forecast()
    payload["minutely_15"]["precipitation"] = [0.0] * 12
    await setup_entry(hass, aioclient_mock, freezer, payload=payload)
    assert hass.states.get("binary_sensor.wohnwagen_gewitterwarnung").state == "off"
    assert hass.states.get("binary_sensor.wohnwagen_regen_in_der_nachsten_stunde").state == "off"
    assert hass.states.get("sensor.wohnwagen_regen_in").state == "unknown"


async def test_solar_settings_used(hass, aioclient_mock, freezer):
    entry = await setup_entry(hass, aioclient_mock, freezer, features=None)
    await set_options(hass, entry, {**ALL, "enable_official_warnings": False}, solar={"pv_power_wp": 400, "pv_tilt": 30, "pv_azimuth": -45, "pv_efficiency": 50})
    q = [c for c in aioclient_mock.mock_calls if str(c[1]).startswith(FORECAST_URL)][-1][1].query
    assert q["tilt"] == "30" and q["azimuth"] == "-45"
    assert float(hass.states.get("sensor.wohnwagen_solarprognose_heute").state) == 0.6  # 3 x 0,4 x 0,5
    # Optionen erneut ohne Solar speichern -> Solarwerte bleiben erhalten
    await set_options(hass, entry, {**ALL, "enable_solar": False})
    assert entry.options["pv_power_wp"] == 400
    assert hass.states.get("sensor.wohnwagen_solarprognose_heute") is None


async def test_disabling_removes_entities(hass, aioclient_mock, freezer):
    entry = await setup_entry(hass, aioclient_mock, freezer)
    registry = er.async_get(hass)
    before = len(er.async_entries_for_config_entry(registry, entry.entry_id))
    await set_options(hass, entry, {k: False for k in ALL})
    after = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert before == 19 and len(after) == 8
    assert hass.states.get("sensor.wohnwagen_amtliche_warnungen") is None


async def test_favorites(hass, aioclient_mock, freezer):
    entry = await setup_entry(hass, aioclient_mock, freezer)
    fav = "select.wohnwagen_lieblingsplatze"
    assert hass.states.get(fav).attributes["options"] == ["–"]
    await hass.services.async_call("button", "press", {"entity_id": "button.wohnwagen_ort_als_lieblingsplatz_merken"}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(fav).attributes["options"] == ["–", "Mamming"]
    # gleicher Ort nochmal -> kein Duplikat
    await hass.services.async_call("button", "press", {"entity_id": "button.wohnwagen_ort_als_lieblingsplatz_merken"}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(fav).attributes["options"] == ["–", "Mamming"]

    # woanders hinfahren, dann Lieblingsplatz wählen
    hass.states.async_set(TRACKER, "not_home", {"latitude": 46.05, "longitude": 14.5})
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=15))
    await hass.async_block_till_done()
    await hass.services.async_call("select", "select_option", {"entity_id": fav, "option": "Mamming"}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get("select.wohnwagen_standortquelle").state == "manual"
    assert hass.states.get(fav).state == "Mamming"
    q = [c for c in aioclient_mock.mock_calls if str(c[1]).startswith(FORECAST_URL)][-1][1].query
    assert q["latitude"] == "45.6780"

    # über die Optionen löschen
    await set_options(hass, entry, ALL, remove=["Mamming"])
    assert hass.states.get(fav).attributes["options"] == ["–"]


async def test_meteoalarm_abroad(hass, aioclient_mock, freezer):
    feed = {"warnings": [
        {"alert": {"info": [
            {"language": "it-IT", "event": "Vento", "severity": "Moderate", "headline": "it", "area": [{"areaDesc": "Friuli Venezia Giulia"}]},
            {"language": "en-GB", "event": "Wind", "severity": "Moderate", "headline": "Yellow wind warning",
             "description": "Strong wind", "onset": "2026-11-07T06:00:00+01:00", "expires": "2026-11-08T00:00:00+01:00",
             "area": [{"areaDesc": "Friuli-Venezia Giulia"}]}]}},
        {"alert": {"info": [{"language": "en-GB", "event": "Rain", "severity": "Severe", "headline": "elsewhere",
                             "expires": "2026-11-08T00:00:00+01:00", "area": [{"areaDesc": "Sicilia"}]}]}},
    ]}
    aioclient_mock.get(METEOALARM_URL.format(country="italy"), json=feed)
    await setup_entry(hass, aioclient_mock, freezer, reverse={"address": {"town": "Grado", "county": "Gorizia",
                                                                          "state": "Friuli Venezia Giulia", "country_code": "it"}})
    warn = hass.states.get("sensor.wohnwagen_amtliche_warnungen")
    assert warn.state == "1" and warn.attributes["quelle"] == "MeteoAlarm"
    assert warn.attributes["warnungen"][0]["ereignis"] == "Wind"
    assert not [c for c in aioclient_mock.mock_calls if str(c[1]).startswith(DWD_URL)]


async def test_warning_service_down_keeps_weather(hass, aioclient_mock, freezer):
    freezer.move_to(NOW)
    await hass.config.async_update(time_zone="Europe/Berlin", language="de")
    aioclient_mock.get(FORECAST_URL, json=forecast())
    aioclient_mock.get(REVERSE_URL, json={"address": {"town": "Mamming", "country_code": "de"}})
    aioclient_mock.get(DWD_URL, exc=TimeoutError())
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    await hass.config_entries.flow.async_configure(result["flow_id"], {"name": "Wohnwagen", "location": {"latitude": 48.6, "longitude": 12.5}})
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(result["flow_id"], {"location": {"latitude": 48.6, "longitude": 12.5}, "update_minutes": 30,
        "awning_gust_kmh": 38, "storm_gust_kmh": 75, "frost_temperature": 2, "enable_official_warnings": True})
    await hass.async_block_till_done()
    assert hass.states.get("weather.wohnwagen_wetter").state == "partlycloudy"
    warn = hass.states.get("sensor.wohnwagen_amtliche_warnungen")
    assert warn.state == "unknown" and "DWD" in warn.attributes["fehler"]


async def test_diagnostics_hide_location(hass, aioclient_mock, freezer):
    entry = await setup_entry(hass, aioclient_mock, freezer)
    await hass.services.async_call("button", "press", {"entity_id": "button.wohnwagen_ort_als_lieblingsplatz_merken"}, blocking=True)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    text = repr(diag)
    assert "45.678" not in text and "13.395" not in text and "Mamming" not in text
    assert diag["features"]["enable_solar"] is True and diag["daten"]["stunden"] == 168
