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
        t_ms = props.get("time")
        points.append({
            "lat": round(float(coords[1]), 4),
            "lng": round(float(coords[0]), 4),
            "alt_km": 0.0,
            "label": f"M{mag} {props.get('place') or ''}".strip(),
            "mag": mag,
            "time_epoch": (t_ms / 1000.0) if isinstance(t_ms, (int, float)) else None,
            "depth_km": float(coords[2]) if len(coords) > 2 and coords[2] is not None else None,
            "place": props.get("place"),
            "source_id": feat.get("id"),
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


# ==========================================================================
# Round 2 sources (added 2026-11-10). Each was verified live before wiring;
# per-source licence verdicts live in DATA_SOURCES.md sections 6-13.
# ==========================================================================

CELESTRAK_GROUP_URL = ("https://celestrak.org/NORAD/elements/gp.php"
                       "?GROUP={group}&FORMAT=tle")
CNEOS_URL = "https://ssd-api.jpl.nasa.gov/fireball.api?limit=100"
SWPC_KP_URL = "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"
SWPC_WIND_URL = "https://services.swpc.noaa.gov/json/rtsw/rtsw_wind_1m.json"
NHC_URL = "https://www.nhc.noaa.gov/CurrentStorms.json"
EMSC_URL = ("https://www.seismicportal.eu/fdsnws/event/1/query"
            "?format=json&limit=1000&minmag=2.5"
            "&start={start}&end={end}")
AIS_URL = "https://meri.digitraffic.fi/api/ais/v1/locations"
NDBC_URL = "https://www.ndbc.noaa.gov/data/latest_obs/latest_obs.txt"
WFIGS_URL = ("https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/"
             "services/WFIGS_Incident_Locations_Current/FeatureServer/0/query"
             "?where=1%3D1"
             "&outFields=IncidentName,IncidentSize,PercentContained,"
             "POOState,POOCounty,FireDiscoveryDateTime"
             "&returnGeometry=true&f=geojson&resultRecordCount=2000")


def _iso_epoch(text: str | None) -> float | None:
    """Parse the ISO-8601 variants the round-2 feeds use (assume UTC)."""
    if not text:
        return None
    t = str(text).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(t)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.strptime(str(text).strip(), fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _fetch_json(url: str, timeout: float = 90.0):
    body, latency_ms, _ = _fetch(url, timeout=timeout)
    import json
    return json.loads(body), {"latency_ms": latency_ms,
                              "response_bytes": len(body)}


def fetch_tle_group(group: str) -> dict:
    body, latency_ms, _ = _fetch(CELESTRAK_GROUP_URL.format(group=group))
    parsed = parse_tle_propagate(body.decode("utf-8", "replace"), time.time())
    parsed["_fetch"] = {"latency_ms": latency_ms, "response_bytes": len(body)}
    return parsed


# --------------------------------------------------------------------------
# NASA/JPL CNEOS — fireball / bolide events (US Government sensors via JPL)
# --------------------------------------------------------------------------

def parse_cneos(payload: dict) -> dict:
    fields = payload.get("fields") or []
    idx = {name: i for i, name in enumerate(fields)}
    points: list[dict] = []
    impacts: list[float] = []
    epochs: list[float] = []
    for row in payload.get("data") or []:
        def get(name):
            i = idx.get(name)
            return row[i] if i is not None and i < len(row) else None
        lat_raw, lon_raw = get("lat"), get("lon")
        if lat_raw is None or lon_raw is None:
            continue
        try:
            lat = float(lat_raw) * (-1 if get("lat-dir") == "S" else 1)
            lng = float(lon_raw) * (-1 if get("lon-dir") == "W" else 1)
            impact = float(get("impact-e")) if get("impact-e") else None
            alt = float(get("alt")) if get("alt") else 0.0
        except (TypeError, ValueError):
            continue
        epoch = _iso_epoch(get("date"))
        if epoch is not None:
            epochs.append(epoch)
        if impact is not None:
            impacts.append(impact)
        points.append({
            "lat": round(lat, 3), "lng": round(lng, 3),
            "alt_km": alt,
            "label": (f"{get('date')} fireball"
                      + (f" — impact energy {impact} kt" if impact is not None else "")),
            "impact_kt": impact, "time_epoch": epoch,
            "date": get("date"), "vel_kms": get("vel"),
        })
    points.sort(key=lambda p: p["time_epoch"] or 0, reverse=True)
    return {
        "points": points,
        "count": len(points),
        "rows_total": len(payload.get("data") or []),
        "max_impact_kt": max(impacts) if impacts else None,
        "feed_epoch": max(epochs) if epochs else None,
        "oldest_epoch": min(epochs) if epochs else None,
    }


def fetch_cneos() -> dict:
    parsed, fetch = None, None
    payload, fetch = _fetch_json(CNEOS_URL)
    parsed = parse_cneos(payload)
    parsed["_fetch"] = fetch
    return parsed


# --------------------------------------------------------------------------
# NOAA SWPC — space weather: planetary K-index + real-time solar wind.
# Panel layer (no globe points): the honest object is a number, not a dot.
# --------------------------------------------------------------------------

def parse_swpc_kp(payload: list) -> dict:
    rows = [r for r in payload if r.get("estimated_kp") is not None]
    if not rows:
        return {"latest_kp": None, "latest_epoch": None, "entries": 0,
                "max_kp_24h": None}
    latest = rows[-1]
    latest_epoch = _iso_epoch(latest.get("time_tag"))
    recent = [r for r in rows
              if latest_epoch and (_iso_epoch(r.get("time_tag")) or 0)
              >= latest_epoch - 86400]
    return {
        "latest_kp": latest.get("estimated_kp"),
        "latest_kp_index": latest.get("kp_index"),
        "latest_epoch": latest_epoch,
        "entries": len(rows),
        "max_kp_24h": max(r["estimated_kp"] for r in recent) if recent else None,
    }


def parse_swpc_wind(payload: list) -> dict:
    active = [r for r in payload
              if r.get("active") and r.get("proton_speed") is not None]
    if not active:
        active = [r for r in payload if r.get("proton_speed") is not None]
    if not active:
        return {"speed_kms": None, "density_pcc": None, "source": None,
                "epoch": None, "entries": 0}
    # rtsw rows arrive newest-first within each source block; take the
    # newest active row overall.
    best = max(active, key=lambda r: _iso_epoch(r.get("time_tag")) or 0)
    return {
        "speed_kms": best.get("proton_speed"),
        "density_pcc": best.get("proton_density"),
        "temperature_k": best.get("proton_temperature"),
        "source": best.get("source"),
        "epoch": _iso_epoch(best.get("time_tag")),
        "entries": len(payload),
    }


def fetch_spaceweather() -> dict:
    kp_payload, kp_fetch = _fetch_json(SWPC_KP_URL)
    wind_payload, wind_fetch = _fetch_json(SWPC_WIND_URL, timeout=120.0)
    return {
        "kp": parse_swpc_kp(kp_payload),
        "wind": parse_swpc_wind(wind_payload),
        "_fetch": {"latency_ms": kp_fetch["latency_ms"] + wind_fetch["latency_ms"],
                   "response_bytes": kp_fetch["response_bytes"]
                   + wind_fetch["response_bytes"]},
    }


# --------------------------------------------------------------------------
# NOAA NHC — active tropical cyclones (often honestly zero)
# --------------------------------------------------------------------------

def parse_nhc(payload: dict) -> dict:
    points: list[dict] = []
    epochs: list[float] = []
    for s in payload.get("activeStorms") or []:
        lat, lng = s.get("latitudeNumeric"), s.get("longitudeNumeric")
        if lat is None or lng is None:
            continue
        epoch = _iso_epoch(s.get("lastUpdate"))
        if epoch is not None:
            epochs.append(epoch)
        points.append({
            "lat": round(float(lat), 3), "lng": round(float(lng), 3),
            "alt_km": 0.0,
            "label": (f"{s.get('name') or s.get('id')} — "
                      f"{s.get('classification') or ''} "
                      f"{s.get('intensity') or ''} kt").strip(),
            "name": s.get("name"), "classification": s.get("classification"),
            "intensity_kt": s.get("intensity"), "pressure_mb": s.get("pressure"),
            "time_epoch": epoch,
            "track_cone_kmz": (s.get("trackCone") or {}).get("kmzFile"),
        })
    return {"points": points, "count": len(points),
            "feed_epoch": max(epochs) if epochs else None}


def fetch_nhc() -> dict:
    payload, fetch = _fetch_json(NHC_URL)
    parsed = parse_nhc(payload)
    parsed["_fetch"] = fetch
    return parsed


# --------------------------------------------------------------------------
# EMSC SeismicPortal — second, independent earthquake catalogue (CC BY 4.0)
# --------------------------------------------------------------------------

def emsc_url(at_unix: float) -> str:
    fmt = "%Y-%m-%dT%H:%M:%S"
    start = datetime.fromtimestamp(at_unix - 86400, tz=timezone.utc).strftime(fmt)
    end = datetime.fromtimestamp(at_unix, tz=timezone.utc).strftime(fmt)
    return EMSC_URL.format(start=start, end=end)


def parse_emsc(payload: dict) -> dict:
    points: list[dict] = []
    mags: list[float] = []
    updates: list[float] = []
    for feat in payload.get("features") or []:
        props = feat.get("properties") or {}
        lat, lng = props.get("lat"), props.get("lon")
        if lat is None or lng is None:
            continue
        mag = props.get("mag")
        upd = _iso_epoch(props.get("lastupdate"))
        if upd is not None:
            updates.append(upd)
        points.append({
            "lat": round(float(lat), 4), "lng": round(float(lng), 4),
            "alt_km": 0.0,
            "label": f"M{mag} {props.get('flynn_region') or ''}".strip(),
            "mag": mag,
            "time_epoch": _iso_epoch(props.get("time")),
            "depth_km": props.get("depth"),
            "place": props.get("flynn_region"),
            "source_id": props.get("unid"),
            "auth": props.get("auth"),
        })
        if isinstance(mag, (int, float)):
            mags.append(float(mag))
    return {
        "points": points,
        "count": len(points),
        "max_mag": max(mags) if mags else None,
        "count_m45_plus": sum(1 for m in mags if m >= 4.5),
        "feed_epoch": max(updates) if updates else None,
    }


def fetch_emsc() -> dict:
    payload, fetch = _fetch_json(emsc_url(time.time()), timeout=120.0)
    parsed = parse_emsc(payload)
    parsed["_fetch"] = fetch
    return parsed


# --------------------------------------------------------------------------
# Fintraffic Digitraffic — AIS vessel locations, Finnish/Baltic waters
# (CC BY 4.0; attribution string in DATA_SOURCES.md). Regional by design.
# --------------------------------------------------------------------------

def parse_ais(payload: dict) -> dict:
    points: list[dict] = []
    for feat in payload.get("features") or []:
        coords = (feat.get("geometry") or {}).get("coordinates") or []
        props = feat.get("properties") or {}
        if len(coords) < 2 or coords[0] is None or coords[1] is None:
            continue
        points.append({
            "lat": round(float(coords[1]), 4), "lng": round(float(coords[0]), 4),
            "alt_km": 0.0,
            "label": f"vessel MMSI {props.get('mmsi')}",
            "mmsi": props.get("mmsi"),
            "sog_kn": props.get("sog"), "cog": props.get("cog"),
            "heading": props.get("heading"),
        })
    lats = [p["lat"] for p in points]
    lngs = [p["lng"] for p in points]
    return {
        "points": points,
        "count": len(points),
        "feed_epoch": _iso_epoch(payload.get("dataUpdatedTime")),
        "bbox": ({"lat_min": min(lats), "lat_max": max(lats),
                  "lng_min": min(lngs), "lng_max": max(lngs)}
                 if points else None),
    }


def fetch_ais() -> dict:
    payload, fetch = _fetch_json(AIS_URL, timeout=120.0)
    parsed = parse_ais(payload)
    parsed["_fetch"] = fetch
    return parsed


# --------------------------------------------------------------------------
# NOAA NDBC — moored buoy latest observations (fixed-format text)
# --------------------------------------------------------------------------

def parse_ndbc(text: str) -> dict:
    points: list[dict] = []
    epochs: list[float] = []
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 8:
            continue
        try:
            lat, lng = float(parts[1]), float(parts[2])
            year, mo, dd = int(parts[3]), int(parts[4]), int(parts[5])
            hh, mm = int(parts[6]), int(parts[7])
            epoch = datetime(year, mo, dd, hh, mm,
                             tzinfo=timezone.utc).timestamp()
        except (ValueError, IndexError):
            continue
        epochs.append(epoch)
        points.append({
            "lat": round(lat, 3), "lng": round(lng, 3), "alt_km": 0.0,
            "label": f"buoy {parts[0]}",
            "station": parts[0], "time_epoch": epoch,
            "wind_dir": parts[8] if len(parts) > 8 else None,
            "wind_ms": parts[9] if len(parts) > 9 else None,
            "water_temp_c": parts[14] if len(parts) > 14 else None,
        })
    return {"points": points, "count": len(points),
            "feed_epoch": max(epochs) if epochs else None}


def fetch_ndbc() -> dict:
    body, latency_ms, _ = _fetch(NDBC_URL)
    parsed = parse_ndbc(body.decode("utf-8", "replace"))
    parsed["_fetch"] = {"latency_ms": latency_ms, "response_bytes": len(body)}
    return parsed


# --------------------------------------------------------------------------
# NIFC WFIGS — current US wildland-fire incident locations (ArcGIS REST).
# The "current" layer includes prescribed burns (names ending RX) — the
# receipt says so; an incident point is a dispatch record, not a flame.
# --------------------------------------------------------------------------

def parse_wfigs(payload: dict) -> dict:
    points: list[dict] = []
    acres: list[float] = []
    rx = 0
    for feat in payload.get("features") or []:
        coords = (feat.get("geometry") or {}).get("coordinates") or []
        props = feat.get("properties") or {}
        if len(coords) < 2 or coords[0] is None or coords[1] is None:
            continue
        name = props.get("IncidentName") or "unnamed incident"
        size = props.get("IncidentSize")
        if isinstance(size, (int, float)):
            acres.append(float(size))
        if " RX" in name.upper() or name.upper().endswith("RX"):
            rx += 1
        disc = props.get("FireDiscoveryDateTime")
        points.append({
            "lat": round(float(coords[1]), 4), "lng": round(float(coords[0]), 4),
            "alt_km": 0.0,
            "label": (f"{name} ({props.get('POOState') or 'US'})"
                      + (f" — {size} acres" if size else "")),
            "name": name, "acres": size,
            "contained_pct": props.get("PercentContained"),
            "state": props.get("POOState"),
            "time_epoch": (disc / 1000.0) if isinstance(disc, (int, float)) else None,
        })
    return {
        "points": points,
        "count": len(points),
        "total_acres": round(sum(acres), 1),
        "largest_acres": max(acres) if acres else None,
        "rx_count": rx,
    }


def fetch_wfigs() -> dict:
    payload, fetch = _fetch_json(WFIGS_URL, timeout=120.0)
    parsed = parse_wfigs(payload)
    parsed["_fetch"] = fetch
    return parsed
