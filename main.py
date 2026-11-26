"""
Nightly soiling run: for every site (or the ones you pass), fetch -> calculate -> ingest.

    python main.py                  # all sites
    python main.py <site_id> ...    # only these sites (for testing)

Soiling is calculated for TODAY (Asia/Karachi), so run it after the day's cleaning data is in.
Re-running the same day is safe: it overwrites that day's soiling value.

To test without writing anything: comment out the ingest_inverter_soiling(...) call below.
"""

import sys
import traceback

import boto3
import pandas as pd

from config import ES_TIMEZONE, OPENWEATHER_API_KEY, PROCESSED_INDEX
from es_fetch import getdata
from site_config import cni_login, get_inverter_ids, get_site_db, get_site_list, get_site_location
from soiling_calc import calc_inverter_soiling, compute_slr
from soiling_ingest import build_site_metrics, ingest_inverter_soiling
from weather import get_current_air_quality_openweather, get_daily_weather


def main(site_ids=None):
    """site_ids: list of site ids; None = every site from get_site_list()"""
    sqs_client = boto3.client("sqs", region_name="ap-southeast-1")
    sqs_url    = "https://sqs.ap-southeast-1.amazonaws.com/167935383433/es-ingestion-insites"

    today      = pd.Timestamp.now(tz=ES_TIMEZONE).tz_localize(None).normalize()
    # date_str   = today.strftime("%Y-%m-%d")
    date_str = (today - pd.Timedelta(days=0)).strftime("%Y-%m-%d")
    week_start = (today - pd.Timedelta(days=7)).strftime("%Y-%m-%d")

    login = cni_login()

    # if site_ids is None:
    #     try:
    #         site_ids = get_site_list(login)
    #     except Exception:
    #         print("get_site_list failed")
    #         raise
    # print(f"Total sites: {len(site_ids)} | soiling date {date_str} | window {week_start} -> {date_str}")


    site_ids = ["8497d810-7b93-41df-81ee-e7847692b596"]

    processed, skipped, failed = [], [], []

    for sid in site_ids:
        sid = str(sid)
        try:
            site_json = get_site_db(sid, login)
            inv_ids   = get_inverter_ids(site_json)
            loc       = get_site_location(site_json)

            if not inv_ids:
                print(f"[{sid}] Skipped: no siteInverterQuantity")
                skipped.append(sid)
                continue
            if loc["latitude"] is None or loc["longitude"] is None:
                print(f"[{sid}] Skipped: no site latitude/longitude")
                skipped.append(sid)
                continue

            # ── Fetch ────────────────────────────────────────────────────────
            df_processed = getdata(PROCESSED_INDEX, week_start, date_str, sid)
            if df_processed is False:
                # don't calculate from a failed fetch: it would write 'no history' values
                print(f"[{sid}] Failed: processed-data fetch failed")
                failed.append(sid)
                continue

            aq      = get_current_air_quality_openweather(loc["latitude"], loc["longitude"], OPENWEATHER_API_KEY)
            weather = get_daily_weather(loc["latitude"], loc["longitude"], date_str)

            # ── Calculate ────────────────────────────────────────────────────
            pm10 = aq["pm10"] if aq else None
            slr  = compute_slr(pm10, weather["RH"], weather["wind"], loc["tilt"])
            soiling = calc_inverter_soiling(
                df_processed, inv_ids, date_str, slr,
                rainfall_inches=weather["rainfall_mm"] / 25.4,
            )

            # ── Verify (printed right before ingestion) ──────────────────────
            print(
                f"[{sid}] '{loc['name']}' {date_str} | rows={len(df_processed)} | SLR={slr:.5f}/day | "
                f"pm10={pm10} RH={weather['RH']:.0f} wind={weather['wind']:.1f} "
                f"tilt={loc['tilt']:.0f} rain={weather['rainfall_mm']:.1f}mm"
            )
            for inv, v in soiling.items():
                print(f"[{sid}]   {inv}: {v:.5f} ({v * 100:.2f}%)")

            # ── Ingest (comment out the next line to test without writing) ───
            ingest_inverter_soiling(
                sid, site_json, date_str, soiling, sqs_client, sqs_url,
                site_metrics=build_site_metrics(slr, pm10, weather),
            )
            processed.append(sid)

        except Exception:
            print(f"[{sid}] Failed:")
            traceback.print_exc()
            failed.append(sid)

    print(f"Soiling done: {len(processed)} processed, {len(skipped)} skipped, {len(failed)} failed")
    if failed:
        print(f"Failed sites: {failed}")


if __name__ == "__main__":
    main(sys.argv[1:] or None)