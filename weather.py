"""
Weather / air quality for one site.

- get_current_air_quality_openweather : current pm2.5 / pm10 / aqi (OpenWeather)
- get_daily_weather                   : rainfall_mm / max RH / max wind for one date (Open-Meteo)
"""

import traceback

import pandas as pd
import requests


def get_current_air_quality_openweather(latitude, longitude, api_key):
    """Return {'pm2_5', 'pm10', 'aqi'} or None on failure."""
    try:
        response = requests.get(
            "http://api.openweathermap.org/data/2.5/air_pollution",
            params={"lat": latitude, "lon": longitude, "appid": api_key},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        if data.get("list"):
            item = data["list"][0]
            comp = item["components"]
            return {
                "pm2_5": comp.get("pm2_5", 0),
                "pm10":  comp.get("pm10", 0),
                "aqi":   item["main"]["aqi"],
            }
        return None

    except Exception as e:
        traceback.print_exc()
        print(f"[WEATHER] Air quality failed for ({latitude}, {longitude}): {e}")
        return None


def get_daily_weather(latitude, longitude, date_str):
    """
    {'rainfall_mm', 'RH', 'wind'} for one date: daily precipitation (mm), max relative
    humidity (%) and max wind speed. On failure returns zeros with ok=False.
    """
    days_ago = (pd.Timestamp.today().normalize() - pd.Timestamp(date_str).normalize()).days

    if days_ago < 7:
        url   = "https://api.open-meteo.com/v1/forecast"
        daily = "precipitation_sum,relative_humidity_2m_max,wind_speed_10m_max"
    else:
        url   = "https://archive-api.open-meteo.com/v1/archive"
        daily = "precipitation_sum,relativehumidity_2m_max,windspeed_10m_max"

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": date_str,
        "end_date": date_str,
        "daily": daily,
        "timezone": "auto",
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        d = response.json()["daily"]

        rh_key   = "relativehumidity_2m_max" if "relativehumidity_2m_max" in d else "relative_humidity_2m_max"
        wind_key = "windspeed_10m_max"       if "windspeed_10m_max" in d       else "wind_speed_10m_max"

        return {
            "rainfall_mm": float(d["precipitation_sum"][0] or 0),
            "RH":          float(d[rh_key][0] or 0),
            "wind":        float(d[wind_key][0] or 0),
            "ok":          True,
        }

    except Exception as e:
        print(f"[WEATHER] Open-Meteo failed ({date_str}): {type(e).__name__}: {e}")
        return {"rainfall_mm": 0.0, "RH": 0.0, "wind": 0.0, "ok": False}