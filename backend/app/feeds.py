"""Feed fetchers and parsers for globereckon.

Each parser is a pure function (bytes/text in, structured layer out) so the
test-suite can run it against recorded fixtures. Fetchers are thin httpx
wrappers that also report latency and payload size for the receipts panel.

Licence/terms per source live in DATA_SOURCES.md. Nothing in this module
redistributes feed data to disk except the small, labelled fixture excerpts
under fixtures/ used by the tests.
"""

from __future__ import annotations

import csv
import io
import math
import os
import time
from datetime import datetime, timezone

import httpx
from sgp4.api import Satrec, jday

USER_AGENT = "globereckon/0.1 (non-commercial content demo; contact: repo README)"

OPENSKY_URL = "https://opensky-network.org/api/states/all"
CELESTRAK_URL = ("https://celestrak.org/NORAD/elements/gp.php"
                 "?GROUP=active&FORMAT=tle")
USGS_URL = ("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/"
            "2.5_day.geojson")
FIRMS_URL = ("https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
             "{key}/VIIRS_SNPP_NRT/-180,-90,180,90/1")


class FeedError(RuntimeError):
    """A feed could not be fetched or parsed; the API surfaces this honestly."""


def _fetch(url: str, timeout: float = 90.0) -> tuple[bytes, int, int]:
    """Return (body, latency_ms, status). Raises FeedError on non-200."""
    started = time.monotonic()
    # Honour a standard HTTPS_PROXY when present (some sandboxes route all
    # egress through one), but disable blanket trust_env: the NO_PROXY list
    # in such environments can contain bracketed IPv6 entries that httpx's
    # mount parser rejects. All feed hosts here are external, so a single
    # explicit proxy (or None on a normal machine) is correct.
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    # SSL_CERT_FILE, when set, names the CA bundle the environment trusts
    # (e.g. an egress proxy's CA); httpx/certifi would miss it otherwise.
    verify = os.environ.get("SSL_CERT_FILE") or True
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True,
                          trust_env=False, proxy=proxy, verify=verify,
                          headers={"User-Agent": USER_AGENT}) as client:
            resp = client.get(url)
    except httpx.HTTPError as exc:  # network-level failure
        raise FeedError(f"fetch failed: {exc.__class__.__name__}") from exc
    latency_ms = int((time.monotonic() - started) * 1000)
    if resp.status_code != 200:
        raise FeedError(f"feed returned HTTP {resp.status_code}")
    return resp.content, latency_ms, resp.status_code


# --------------------------------------------------------------------------
# OpenSky — live aircraft state vectors (anonymous, non-commercial use only)
# State-vector indices per the OpenSky API documentation:
#   0 icao24, 1 callsign, 2 origin_country, 3 time_position, 4 last_contact,
#   5 longitude, 6 latitude, 7 barometric altitude (m), 8 on_ground,
#   9 velocity (m/s), 13 geometric altitude (m)
# --------------------------------------------------------------------------

def parse_opensky(payload: dict) -> dict:
    feed_epoch = payload.get("time")
    states = payload.get("states") or []
    points: list[dict] = []
    ages: list[float] = []
    on_ground = 0
    for s in states:
        if len(s) < 14 or s[5] is None or s[6] is None:
            continue
        alt_m = s[13] if s[13] is not None else s[7]
        points.append({
            "lat": round(float(s[6]), 4),
            "lng": round(float(s[5]), 4),
            "alt_km": round((alt_m or 0) / 1000.0, 2),
            "label": (s[1] or s[0] or "").strip(),
        })
        if s[8]:
            on_ground += 1
        if feed_epoch is not None and s[3] is not None:
            ages.append(feed_epoch - s[3])
    ages.sort()
    median_age = ages[len(ages) // 2] if ages else None
    return {
        "points": points,
        "feed_epoch": feed_epoch,
        "states_total": len(states),
        "positioned": len(points),
        "on_ground": on_ground,
        "median_position_age_s": median_age,
    }


def fetch_opensky() -> dict:
    body, latency_ms, _ = _fetch(OPENSKY_URL)
    import json
    parsed = parse_opensky(json.loads(body))
    parsed["_fetch"] = {"latency_ms": latency_ms, "response_bytes": len(body)}
    return parsed


# --------------------------------------------------------------------------
# CelesTrak — GP element sets (TLE) propagated with SGP4.
# Positions are computed at fetch time; the receipt reports how old the
# underlying element sets are, because that is the honest freshness story.
# --------------------------------------------------------------------------

def _tle_epoch(line1: str) -> float | None:
    """Epoch (unix seconds) encoded in TLE line 1, columns 19-32."""
    try:
        year2 = int(line1[18:20])
        day = float(line1[20:32])
    except (ValueError, IndexError):
        return None
    year = 2000 + year2 if year2 < 57 else 1900 + year2
    jan1 = datetime(year, 1, 1, tzinfo=timezone.utc).timestamp()
    return jan1 + (day - 1.0) * 86400.0


def _gmst_deg(unix_s: float) -> float:
    """Greenwich mean sidereal time in degrees (standard low-precision form)."""
    jd = unix_s / 86400.0 + 2440587.5
    t = (jd - 2451545.0) / 36525.0
    gmst = (280.46061837 + 360.98564736629 * (jd - 2451545.0)
            + 0.000387933 * t * t - (t * t * t) / 38710000.0)
    return gmst % 360.0


def parse_tle_propagate(tle_text: str, at_unix: float) -> dict:
    lines = [ln.rstrip("\n") for ln in tle_text.splitlines() if ln.strip()]
    records: list[tuple[str, str, str]] = []
    i = 0
    while i < len(lines):
        if lines[i].startswith("1 ") and i + 1 < len(lines) \
                and lines[i + 1].startswith("2 "):
            records.append(("", lines[i], lines[i + 1]))
            i += 2
        elif i + 2 < len(lines) and lines[i + 1].startswith("1 ") \
                and lines[i + 2].startswith("2 "):
            records.append((lines[i].strip(), lines[i + 1], lines[i + 2]))
            i += 3
        else:
            i += 1

    when = datetime.fromtimestamp(at_unix, tz=timezone.utc)
    jd, fr = jday(when.year, when.month, when.day,
                  when.hour, when.minute, when.second + when.microsecond / 1e6)
    gmst = _gmst_deg(at_unix)
    points: list[dict] = []
    epoch_ages_h: list[float] = []
    failed = 0
    for name, l1, l2 in records:
        epoch = _tle_epoch(l1)
        if epoch is not None:
            epoch_ages_h.append((at_unix - epoch) / 3600.0)
        try:
            sat = Satrec.twoline2rv(l1, l2)
            err, r, _v = sat.sgp4(jd, fr)
            if err != 0:
                failed += 1
                continue
        except Exception:
            failed += 1
            continue
        x, y, z = r
        radius = math.sqrt(x * x + y * y + z * z)
        lat = math.degrees(math.asin(z / radius))
        lon = math.degrees(math.atan2(y, x)) - gmst
        lon = (lon + 540.0) % 360.0 - 180.0
        points.append({
            "lat": round(lat, 3),
            "lng": round(lon, 3),
            "alt_km": round(radius - 6378.137, 1),
            "label": name,
        })
    epoch_ages_h.sort()
    median_age_h = epoch_ages_h[len(epoch_ages_h) // 2] if epoch_ages_h else None
    return {
        "points": points,
        "elements_total": len(records),
        "propagated_ok": len(points),
        "propagation_failed": failed,
        "median_epoch_age_h": median_age_h,
    }


def fetch_celestrak() -> dict:
    body, latency_ms, _ = _fetch(CELESTRAK_URL)
    parsed = parse_tle_propagate(body.decode("utf-8", "replace"), time.time())
    parsed["_fetch"] = {"latency_ms": latency_ms, "response_bytes": len(body)}
    return parsed


# --------------------------------------------------------------------------
# USGS — earthquake GeoJSON feed (US Government, public domain)
# --------------------------------------------------------------------------

def parse_usgs(payload: dict) -> dict:
    meta = payload.get("metadata") or {}
    generated_ms = meta.get("generated")
    points: list[dict] = []
    mags: list[float] = []
    for feat in payload.get("features") or []:
        coords = (feat.get("geometry") or {}).get("coordinates") or []
        props = feat.get("properties") or {}
        if len(coords) < 2 or coords[0] is None or coords[1] is None:
            continue
        mag = props.get("mag")
        points.append({
            "lat": round(float(coords[1]), 4),
            "lng": round(float(coords[0]), 4),
            "alt_km": 0.0,
            "label": f"M{mag} {props.get('place') or ''}".strip(),
            "mag": mag,
        })
        if isinstance(mag, (int, float)):
            mags.append(float(mag))
    return {
        "points": points,
        "feed_epoch": (generated_ms / 1000.0) if generated_ms else None,
        "count": len(points),
        "max_mag": max(mags) if mags else None,
        "count_m45_plus": sum(1 for m in mags if m >= 4.5),
    }


def fetch_usgs() -> dict:
    body, latency_ms, _ = _fetch(USGS_URL)
    import json
    parsed = parse_usgs(json.loads(body))
    parsed["_fetch"] = {"latency_ms": latency_ms, "response_bytes": len(body)}
    return parsed


# --------------------------------------------------------------------------
# NASA FIRMS — active-fire detections. Requires a free MAP_KEY obtained by
# the operator's own signup; without one the layer reports itself OFF.
# --------------------------------------------------------------------------

def parse_firms_csv(text: str) -> dict:
    reader = csv.DictReader(io.StringIO(text))
    points: list[dict] = []
    for row in reader:
        try:
            lat = float(row["latitude"])
            lng = float(row["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        points.append({
            "lat": round(lat, 4),
            "lng": round(lng, 4),
            "alt_km": 0.0,
            "label": f"fire detection ({row.get('satellite', '?')})",
        })
    return {"points": points, "count": len(points)}


def fetch_firms() -> dict | None:
    """None means: no MAP_KEY configured — the layer is honestly off."""
    key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    if not key:
        return None
    body, latency_ms, _ = _fetch(FIRMS_URL.format(key=key), timeout=120.0)
    parsed = parse_firms_csv(body.decode("utf-8", "replace"))
    parsed["_fetch"] = {"latency_ms": latency_ms, "response_bytes": len(body)}
    return parsed
