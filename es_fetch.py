"""
Elasticsearch data fetching.

- getdata : per-site processed data (filters by siteId.keyword + time range)

Returns a DataFrame indexed by @timestamp, or False on failure.
Nested fields are flattened with dots, e.g. column "inverters.INV9.clean".
"""

import traceback

import pandas as pd
import requests
from pandas import json_normalize

from config import (
    ES_BASE_URL, ES_USER, ES_PASSWORD, ES_SCROLL_TTL, ES_PAGE_SIZE, ES_TIMEZONE,
)

ES_AUTH    = (ES_USER, ES_PASSWORD)
ES_HEADERS = {"Content-Type": "application/json", "Accept-Encoding": "gzip"}
TIMEOUT    = 60


def _scroll_all(index, query):
    """
    Run a scrolled search against `index` using `query` and return all hits as a list.
    Returns False on any error.
    """
    try:
        resp = requests.post(
            f"{ES_BASE_URL}/{index}/_search?scroll={ES_SCROLL_TTL}",
            auth=ES_AUTH,
            headers=ES_HEADERS,
            json={**query, "size": ES_PAGE_SIZE, "sort": [{"@timestamp": {"order": "asc"}}]},
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            print(f"[ES] Initial search failed ({resp.status_code}): {resp.text[:200]}")
            return False

        body      = resp.json()
        scroll_id = body["_scroll_id"]
        hits      = body["hits"]["hits"]

        while True:
            resp = requests.post(
                f"{ES_BASE_URL}/_search/scroll",
                auth=ES_AUTH,
                headers={"Content-Type": "application/json"},
                json={"scroll": ES_SCROLL_TTL, "scroll_id": scroll_id},
                timeout=TIMEOUT,
            )
            page = resp.json()["hits"]["hits"]
            if not page:
                break
            hits.extend(page)

        return hits

    except Exception:
        traceback.print_exc()
        return False


def _hits_to_df(hits):
    """Normalise a list of ES hits into a clean DataFrame indexed by @timestamp."""
    if not hits:
        # no documents in range -> empty frame (json_normalize([]) has no @timestamp column)
        return pd.DataFrame(index=pd.DatetimeIndex([], name="@timestamp"))

    df = json_normalize(hits)
    df = df.drop(columns=["_source.logger.@timestamp"], errors="ignore")
    df.columns = [c.replace("_source.", "").replace("logger.", "") for c in df.columns]
    df["@timestamp"] = pd.to_datetime(df["@timestamp"])
    df.set_index("@timestamp", inplace=True)
    return df


def getdata(index, start, end, site_id):
    """Return processed-data DataFrame filtered by site and date range, or False on failure."""
    query = {
        "query": {
            "bool": {
                "must": [
                    {"term":  {"siteId.keyword": site_id}},
                    {"range": {"@timestamp": {"gte": start, "lte": end, "time_zone": ES_TIMEZONE}}},
                ]
            }
        }
    }
    hits = _scroll_all(index, query)
    if hits is False:
        return False
    return _hits_to_df(hits)
