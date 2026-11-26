"""
Soiling calculation.

- compute_slr             : site-level daily soiling loss rate from PM10, humidity, wind, tilt
- calc_inverter_soiling   : per-inverter soiling ratio for a date

Rule per inverter, for a target date:
  - washed that day (inverters.INV<n>.clean == 1)  -> soiling = 0
  - otherwise -> previous soiling + today's SLR, capped at MAX_SOILING

Previous soiling comes from inverters.INV<n>.soiling in the processed-data window
(latest value before the target date, so a missed day doesn't reset to 0).
"""

import numpy as np
import pandas as pd

from config import (
    BASE_SLR, MIN_SLR, MAX_SLR, MAX_SOILING, CLEANING_THRESHOLD, DEFAULT_TILT,
)


def compute_slr(pm10, rh, wind, tilt):
    """
    Daily soiling loss rate (ratio per day).
    Falls back to BASE_SLR when PM10 is missing / zero.
    """
    tilt = DEFAULT_TILT if tilt is None else tilt
    slr = BASE_SLR

    if pm10 is not None and pm10 > 0:
        pm_factor       = np.clip(pm10 / 50.0, 0.5, 3.0)
        humidity_factor = 1 + (rh / 2000.0)

        if wind < 2:
            wind_factor = 1.15
        elif wind > 8:
            wind_factor = 0.90
        else:
            wind_factor = 1.0

        if tilt < 10:
            tilt_factor = 1.3
        elif tilt < 20:
            tilt_factor = 1.15
        elif tilt > 45:
            tilt_factor = 0.85
        else:
            tilt_factor = 1.0

        slr = BASE_SLR * pm_factor * humidity_factor * wind_factor * tilt_factor

    return float(np.clip(slr, MIN_SLR, MAX_SLR))


def calc_inverter_soiling(df_processed, inv_ids, date, slr, rainfall_inches=0.0):
    """
    Returns {inv_id: soiling_ratio} for `date`.

    df_processed    : DataFrame from getdata() for the window ending on `date` (may be empty)
    slr             : daily soiling loss rate (ratio per day)
    rainfall_inches : rain on `date`; >= CLEANING_THRESHOLD resets every inverter to 0
    """
    date = pd.Timestamp(date).tz_localize(None).normalize()

    df = df_processed.copy()
    df["_day"] = df.index.tz_localize(None).normalize()

    rain_wash = rainfall_inches >= CLEANING_THRESHOLD
    result = {}

    for inv in inv_ids:
        clean_col = f"inverters.{inv}.clean"
        soil_col  = f"inverters.{inv}.soiling"

        # 1) washed on the target date?
        washed = False
        if clean_col in df.columns:
            day_clean = pd.to_numeric(df.loc[df["_day"] == date, clean_col], errors="coerce")
            washed = bool((day_clean == 1).any())

        if washed or rain_wash:
            result[inv] = 0.0
            continue

        # 2) not washed: previous soiling + today's increment
        prev = 0.0
        if soil_col in df.columns:
            earlier = df.loc[df["_day"] < date, ["_day", soil_col]].copy()
            earlier[soil_col] = pd.to_numeric(earlier[soil_col], errors="coerce")
            earlier = earlier.dropna(subset=[soil_col]).sort_values("_day")
            if not earlier.empty:
                prev = float(earlier[soil_col].iloc[-1])

        result[inv] = float(min(prev + slr, MAX_SOILING))

    return result
