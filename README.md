# Solar Soiling Loss Estimator

A nightly pipeline that estimates a **daily soiling ratio for every inverter** at every solar site, using air quality, weather and cleaning records. Results are pushed to Elasticsearch (via SQS) for dashboards.

The ratio is a value from `0` to `0.25` (0 – 25 %) representing output lost to dust accumulating on the panels. It is a **rule-based model estimate**, not a measurement from plant production data, and its constants are not fitted to measured losses.

## How it works

For each inverter, on the target date (today in `Asia/Karachi`), in this order:

1. **Washed that day** (`inverters.INV<n>.clean == 1` on any document dated that day) → soiling = `0`
2. **Rain wash** (precipitation ≥ 0.3 in ≈ 7.62 mm) → soiling = `0` for *every* inverter at the site
3. **Otherwise** → `previous soiling + today's SLR`, capped at `0.25`

"Previous soiling" is the latest non-empty `inverters.INV<n>.soiling` value dated before the target day within a 7-day window. A missed run doesn't reset anything; if the window has no earlier value, it starts from `0`.

### Soiling loss rate (SLR)

One value per site per day:

```
SLR = 0.002 × PM10 factor × humidity factor × wind factor × tilt factor
```

| Factor | Input | Rule |
|---|---|---|
| PM10 | PM10 (µg/m³) | `PM10 / 50`, clipped to 0.5 – 3.0 |
| Humidity | max daily RH (%) | `1 + RH / 2000` (1.00 – 1.05) |
| Wind | max daily wind speed | `< 2` → 1.15, `2 – 8` → 1.00, `> 8` → 0.90 |
| Tilt | panel tilt (°) | `< 10` → 1.30, `10 – 20` → 1.15, `20 – 45` → 1.00, `> 45` → 0.85 |

If PM10 is missing or zero, the SLR falls back to the base rate (`0.002`). The final SLR is clipped to `0.0005 – 0.01` per day.

**Worked example:** PM10 = 80, RH = 60 %, wind = 4, tilt = 20° → `0.002 × 1.6 × 1.03 × 1.0 × 1.0 ≈ 0.0033` per day (0.33 %/day).

For the full methodology, edge cases and error handling, see [`docs/Soiling_Calculation_Logic_and_Methodology.pdf`](docs/Soiling_Calculation_Logic_and_Methodology.pdf).

## Pipeline flow

```
CNI API login ─► site list ─► site config (inverters, lat/lon, tilt)
                                   │
        Elasticsearch (7-day history, clean flags, previous soiling)
                                   │
   OpenWeather (current PM10) + Open-Meteo (rain, humidity, wind)
                                   │
                         SLR ─► per-inverter soiling
                                   │
                  SQS ─► consumer ─► Elasticsearch (partial update)
```

A failure at one site is logged and the loop continues. The job prints how many sites were processed, skipped and failed.

## Project structure

| File | Purpose |
|---|---|
| `main.py` | Command-line entry point (all sites, or ones passed as arguments) |
| `run_soiling.py` | `run_soiling()` entry point for a cron job / Lambda handler |
| `config.py` | Configuration and model constants; secrets come from environment variables |
| `site_config.py` | CNI API helpers: login, site list, site config, inverter IDs, location/tilt |
| `es_fetch.py` | Scrolled Elasticsearch query returning a DataFrame indexed by `@timestamp` |
| `weather.py` | OpenWeather air quality (PM10) and Open-Meteo daily weather |
| `soiling_calc.py` | `compute_slr()` and `calc_inverter_soiling()` |
| `soiling_ingest.py` | Builds and sends the Elasticsearch `update` message to SQS |

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env      # fill in your values, then load them into your environment
```

Required environment variables are listed in `.env.example`. **Never commit real credentials.**

## Usage

```bash
python main.py                  # all sites
python main.py <site_id> ...    # only the given sites (for testing)
```

From a Lambda handler or cron job:

```python
import boto3
from config import SQS_URL
from run_soiling import run_soiling

sqs = boto3.client("sqs", region_name="ap-southeast-1")
run_soiling(sqs, SQS_URL, site_ids=["<site id>"])   # one site
run_soiling(sqs, SQS_URL)                           # all sites
```

Run it **after the day's cleaning data is in**. Re-running the same day is safe: it overwrites that day's soiling value and nothing else.

To test without writing anything, comment out the `ingest_inverter_soiling(...)` call.

## Ingestion

One message per site per run is sent to SQS as an Elasticsearch `update` with `doc_as_upsert`. The document ID is `sha256("<siteId>_<YYYY-MM-DD>")`, so the soiling values merge into the existing day document without touching `inverters.INV<n>.clean` or other fields.

Fields written: `@timestamp`, `siteId`, `siteName`, `inverters.INV<n>.soiling`, plus site-level inputs for dashboards (`soiling_slr`, `soiling_pm10`, `soiling_rh`, `soiling_wind`, `soiling_rainfall_mm`). Weather fields are omitted if Open-Meteo failed, so dashboards show a gap instead of a false zero.

## Known limitations

- **PM10 is a live reading** taken when the job runs, so back-dated runs use today's air quality.
- **Wind thresholds (2 and 8) look like m/s, but Open-Meteo returns km/h** by default, so the wind factor sits at 0.90 almost every day. Consider requesting `wind_speed_unit=ms`.
- **Open-Meteo failure** substitutes zeros for rain, humidity and wind (no rain wash, wind factor 1.15).
- The wash flag is binary; partial cleaning is not modelled.
- Rain wash uses model-based precipitation at the site coordinates (not a rain gauge) and applies to all inverters at a site equally.
- Inverters are assumed to be numbered consecutively from `INV1`.
- Documents are assigned to days by their stored `@timestamp` date, while the target date comes from Karachi time.
- Back-fills older than 7 days use Open-Meteo's archive endpoint, which may not accept the requested variables.
- The job sees success when SQS accepts the message; write errors in the consumer are not visible to it.

## Data sources

- **CNI API:** site configuration (inverter count, coordinates, tilt, name)
- **Elasticsearch:** processed data (clean flags, previous soiling)
- **[OpenWeather Air Pollution API](https://openweathermap.org/api/air-pollution):** PM10
- **[Open-Meteo](https://open-meteo.com/):** precipitation, humidity, wind
