"""
Central configuration for the soiling pipeline.

Secrets are read from environment variables (Lambda env vars / Secrets Manager),
never hardcoded. Set these before running:

    ES_BASE_URL, ES_USER, ES_PASSWORD
    OPENWEATHER_API_KEY
    CNI_API_BASE, CNI_API_KEY, CNI_USER, CNI_PASSWORD
    SQS_URL                                            (queue the results are sent to)
"""

import os

# ── Elasticsearch ────────────────────────────────────────────────────────────
ES_BASE_URL   = os.environ.get("ES_BASE_URL", "")
ES_USER       = os.environ.get("ES_USER", "")
ES_PASSWORD   = os.environ.get("ES_PASSWORD", "")
ES_SCROLL_TTL = "15m"
ES_PAGE_SIZE  = 10000
ES_TIMEZONE   = "Asia/Karachi"

PROCESSED_INDEX = "site-cni-processed-data"

# ── Weather / air quality ────────────────────────────────────────────────────
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY", "")

# ── CNI API (site-config lookup) ─────────────────────────────────────────────
CNI_API_BASE     = os.environ.get("CNI_API_BASE", "")
CNI_API_KEY      = os.environ.get("CNI_API_KEY", "")
CNI_USER         = os.environ.get("CNI_USER", "")
CNI_PASSWORD     = os.environ.get("CNI_PASSWORD", "")
CNI_LOGIN_PARAMS = {"regId": "<device id for push notification>", "deviceName": "<device model>"}

# ── Ingestion queue ──────────────────────────────────────────────────────────
SQS_URL = os.environ.get("SQS_URL", "")

# ── Soiling model constants ──────────────────────────────────────────────────
BASE_SLR            = 0.002   # base soiling loss rate, ratio per day (0.2 %/day)
MIN_SLR             = 0.0005
MAX_SLR             = 0.01
MAX_SOILING         = 0.25    # cap on accumulated soiling (25 %)
CLEANING_THRESHOLD  = 0.3     # inches of rain that counts as a natural wash
DEFAULT_TILT        = 25      # degrees, used when siteInfo has no sitePanelTilt
