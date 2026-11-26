"""
CNI API helpers.

- cni_login         : log in, returns the parsed login response (contains the token)
- get_site_list     : list of all site ids for the logged-in user
- get_site_db       : site-config JSON for one site
- get_inverter_ids  : ['INV1', 'INV2', ...] from siteInfo.siteInverterQuantity
- get_site_location : name / latitude / longitude / tilt from siteInfo
"""

import json

import requests

from config import CNI_API_BASE, CNI_API_KEY, CNI_USER, CNI_PASSWORD, CNI_LOGIN_PARAMS, DEFAULT_TILT


def cni_login():
    """Log in to the CNI API and return the parsed login response (contains the token)."""
    resp = requests.post(
        f"{CNI_API_BASE}/login",
        data=json.dumps({"username": CNI_USER, "password": CNI_PASSWORD}),
        headers={
            "content-type": "application/json",
            "accept-encoding": "gzip",
            "x-api-key": CNI_API_KEY,
        },
        params=CNI_LOGIN_PARAMS,
        timeout=30,
    )
    return resp.json()


def get_site_list(login_response):
    """Return the list of site ids for the logged-in user."""
    resp = requests.get(
        f"{CNI_API_BASE}/user-sites",
        headers={
            "authorization": login_response["response"]["token"],
            "x-api-key": CNI_API_KEY,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return [site["siteId"] for site in resp.json()]


def get_site_db(site_id, login_response):
    """Fetch the site-config JSON for `site_id`."""
    resp = requests.get(
        f"{CNI_API_BASE}/site-config",
        params={"siteId": str(site_id)},
        headers={
            "authorization": login_response["response"]["token"],
            "x-api-key": CNI_API_KEY,
        },
        timeout=30,
    )
    return json.loads(resp.text)


def get_inverter_ids(site_json):
    """['INV1', 'INV2', ...] from siteInfo.siteInverterQuantity (empty if missing / invalid)."""
    qty = site_json.get("siteInfo", {}).get("siteInverterQuantity", 0)
    try:
        qty = int(qty)
    except (TypeError, ValueError):
        qty = 0
    return [f"INV{i}" for i in range(1, qty + 1)]


def get_site_location(site_json):
    """Return dict with name, latitude, longitude, tilt."""
    info = site_json.get("siteInfo", {})
    try:
        tilt = float(info.get("sitePanelTilt", DEFAULT_TILT))
    except (TypeError, ValueError):
        tilt = float(DEFAULT_TILT)
    return {
        "name":      info.get("siteName", ""),
        "latitude":  info.get("siteLatitude"),
        "longitude": info.get("siteLongitude"),
        "tilt":      tilt,
    }
