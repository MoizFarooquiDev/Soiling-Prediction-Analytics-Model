"""
Ingestion: push inverters.INV<n>.soiling into site-cni-processed-data via SQS.

Uses the same _id scheme as ingest_daily_forecast (sha256 of '<sid>_<YYYY-MM-DD>') and a
partial `update` with doc_as_upsert, so it merges into the existing day doc. Nested objects
are deep-merged, so inverters.INV<n>.clean and the forecast fields are left untouched.
"""

import hashlib
import json

import pandas as pd

from config import PROCESSED_INDEX


def build_site_metrics(slr, pm10, weather):
    """
    Site-level inputs of the soiling calc, named as the index fields (for the dashboard):
      soiling_slr, soiling_pm10, soiling_rh, soiling_wind, soiling_rainfall_mm
    Weather values are left out when the Open-Meteo call failed (get_daily_weather returns
    zeros then), so the dashboard shows a gap instead of a false 0.
    """
    metrics = {"soiling_slr": slr, "soiling_pm10": pm10}   # pm10 is None if air quality failed
    if weather.get("ok", True):
        metrics["soiling_rh"]          = weather["RH"]
        metrics["soiling_wind"]        = weather["wind"]
        metrics["soiling_rainfall_mm"] = weather["rainfall_mm"]
    return metrics


def ingest_inverter_soiling(sid, site_json, date, soiling_by_inv, sqs_client, sqs_url, site_metrics=None):
    """
    sid            : site id
    site_json      : site config (used for siteName)
    date           : the day the soiling applies to ('YYYY-MM-DD' or Timestamp)
    soiling_by_inv : {'INV1': 0.012, 'INV2': 0.0, ...} (ratios)
    site_metrics   : optional site-level values stored on the same day doc, see build_site_metrics();
                     None values are skipped (a null would overwrite an existing value)
    """
    date_str  = pd.Timestamp(date).strftime("%Y-%m-%d")
    site_name = site_json.get("siteInfo", {}).get("siteName", "")

    action = {
        "update": {
            "_index": PROCESSED_INDEX,
            "_id": hashlib.sha256(f"{sid}_{date_str}".encode()).hexdigest(),
            "retry_on_conflict": 1,
        }
    }
    doc = {
        "@timestamp": date_str,
        "siteId":     sid,
        "siteName":   site_name,
        "inverters":  {inv: {"soiling": float(v)} for inv, v in soiling_by_inv.items()},
    }
    doc.update({k: float(v) for k, v in (site_metrics or {}).items() if v is not None})

    body = {"doc": doc, "doc_as_upsert": True}

    payload = {"message": json.dumps(action) + "\n" + json.dumps(body) + "\n"}
    response = sqs_client.send_message(QueueUrl=sqs_url, MessageBody=json.dumps(payload))
    status = response["ResponseMetadata"]["HTTPStatusCode"]
    print(f"[{sid}] Soiling ingest: {status}")
    return status