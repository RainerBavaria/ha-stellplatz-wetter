"""Nachgebaute Open-Meteo-Antworten (timeformat=unixtime, timezone=auto)."""
from datetime import UTC, datetime, timedelta

BERLIN_MIDNIGHT = datetime(2026, 11, 6, 23, tzinfo=UTC)  # 7.11. 00:00 Ortszeit


def forecast(base_temp: float = 2.0, gust_peak: float = 20.0, code_day: int = 2) -> dict:
    hours = [BERLIN_MIDNIGHT + timedelta(hours=i) for i in range(168)]
    local = [(h.hour + 1) % 24 for h in hours]
    temp = [base_temp + (lh if lh <= 14 else 28 - lh) * 0.5 for lh in local]
    is_day = [1 if 7 <= lh < 17 else 0 for lh in local]
    gusts = [gust_peak if i in (11, 12) else 10.0 for i in range(168)]
    hourly = {
        "time": [int(h.timestamp()) for h in hours],
        "temperature_2m": temp, "relative_humidity_2m": [80] * 168, "dew_point_2m": [0.5] * 168,
        "apparent_temperature": [t - 1 for t in temp], "precipitation_probability": [20] * 168, "precipitation": [0.0] * 168,
        "weather_code": [code_day if d else 3 for d in is_day], "cloud_cover": [50] * 168, "pressure_msl": [1021.5] * 168,
        "wind_speed_10m": [6.0] * 168, "wind_direction_10m": [250] * 168, "wind_gusts_10m": gusts, "uv_index": [0.5] * 168, "is_day": is_day,
    }
    days = [BERLIN_MIDNIGHT + timedelta(days=d) for d in range(7)]
    daily = {
        "time": [int(d.timestamp()) for d in days], "weather_code": [61, 3, 3, 2, 80, 0, 1],
        "temperature_2m_max": [9, 8, 8, 10, 10, 12, 11], "temperature_2m_min": [2, 2, 2, 6, 6, 8, 5],
        "precipitation_sum": [1.2, 0, 0, 0, 3.4, 0, 0], "precipitation_probability_max": [60, 10, 5, 10, 80, 0, 5],
        "wind_speed_10m_max": [12] * 7, "wind_gusts_10m_max": [30] * 7, "wind_direction_10m_dominant": [250] * 7,
        "uv_index_max": [1.5] * 7,
        "sunrise": [int((d + timedelta(hours=6, minutes=10)).timestamp()) for d in days],
        "sunset": [int((d + timedelta(hours=15, minutes=40)).timestamp()) for d in days],
    }
    now = datetime(2026, 11, 7, 9, 15, tzinfo=UTC)
    current = {"time": int(now.timestamp()), "interval": 900, "temperature_2m": 6.8, "relative_humidity_2m": 78,
               "apparent_temperature": 4.9, "is_day": 1, "precipitation": 0.0, "weather_code": code_day, "cloud_cover": 40,
               "pressure_msl": 1022.3, "wind_speed_10m": 7.2, "wind_direction_10m": 240, "wind_gusts_10m": 15.1}
    return {"latitude": 48.65, "longitude": 12.5, "utc_offset_seconds": 3600, "timezone": "Europe/Berlin",
            "timezone_abbreviation": "GMT+1", "elevation": 380, "current": current, "hourly": hourly, "daily": daily}
