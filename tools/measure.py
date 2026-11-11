#!/usr/bin/env python3
"""Live measurement run for globereckon (round 2: all layers).

Fetches every feed once (respecting each source's quota/usage policy),
writes results/measurements.json with the real numbers the README and the
video pack cite, and records labelled excerpts of the real responses as
test fixtures under fixtures/. Fixture excerpts are excerpts — the wrapper
says so, and the full counts live in measurements.json.

Run:  .venv/bin/python tools/measure.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import feeds, receipts  # noqa: E402

NOTE = ("Excerpt of a real recorded response (see recorded_at). "
        "Full-response counts are in results/measurements.json. "
        "Never presented as live.")


def _write_fixture(name: str, recorded_at: float, payload=None,
                   text: str | None = None, payload_text: str | None = None):
    obj: dict = {"recorded_at": recorded_at, "note": NOTE}
    if payload is not None:
        obj["payload"] = payload
    if text is not None:
        obj["text"] = text
    if payload_text is not None:
        obj["payload_text"] = payload_text
    (ROOT / "fixtures" / name).write_text(json.dumps(obj), encoding="utf-8")


def main() -> int:
    out: dict = {"measured_at_unix": time.time(), "layers": {}}
    L = out["layers"]

    # --- OpenSky: one anonymous global call (4-credit class; quota 400/day)
    body, latency_ms, _ = feeds._fetch(feeds.OPENSKY_URL)
    payload = json.loads(body)
    parsed = feeds.parse_opensky(payload)
    fetched_at = time.time()
    cov = receipts.coverage_summary(parsed["points"])
    L["flights"] = {
        "source": "OpenSky Network /api/states/all (anonymous)",
        "response_bytes": len(body),
        "fetch_latency_ms": latency_ms,
        "feed_epoch": parsed["feed_epoch"],
        "staleness_s_at_fetch": receipts.staleness_s(fetched_at,
                                                    parsed["feed_epoch"]),
        "states_total": parsed["states_total"],
        "positioned": parsed["positioned"],
        "on_ground": parsed["on_ground"],
        "median_position_age_s": parsed["median_position_age_s"],
        "coverage": cov,
    }
    _write_fixture("opensky_excerpt.json", fetched_at, payload={
        "time": payload.get("time"),
        "states": (payload.get("states") or [])[:400]})

    # --- CelesTrak: active group TLE, propagated now + sub-layer groups
    body, latency_ms, _ = feeds._fetch(feeds.CELESTRAK_URL)
    text = body.decode("utf-8", "replace")
    fetched_at = time.time()
    parsed = feeds.parse_tle_propagate(text, fetched_at)
    stations = feeds.fetch_tle_group("stations")
    stations.pop("_fetch", None)
    starlink = feeds.fetch_tle_group("starlink")
    starlink.pop("_fetch", None)
    L["satellites"] = {
        "source": "CelesTrak GP, GROUP=active, FORMAT=tle",
        "response_bytes": len(body),
        "fetch_latency_ms": latency_ms,
        "elements_total": parsed["elements_total"],
        "propagated_ok": parsed["propagated_ok"],
        "propagation_failed": parsed["propagation_failed"],
        "median_epoch_age_h": parsed["median_epoch_age_h"],
        "sublayers": {
            "starlink_in_active_by_name": sum(
                1 for p in parsed["points"]
                if (p.get("label") or "").upper().startswith("STARLINK")),
            "starlink_group_elements": starlink["elements_total"],
            "stations_group_elements": stations["elements_total"],
            "stations_group_propagated": stations["propagated_ok"],
        },
    }
    lines = text.splitlines()
    _write_fixture("celestrak_excerpt.json", fetched_at,
                   text="\n".join(lines[:90]))
    sbody, _, _ = feeds._fetch(feeds.CELESTRAK_GROUP_URL.format(group="stations"))
    slines = sbody.decode("utf-8", "replace").splitlines()
    _write_fixture("celestrak_stations_excerpt.json", fetched_at,
                   text="\n".join(slines[:90]))

    # --- USGS
    body, latency_ms, _ = feeds._fetch(feeds.USGS_URL)
    payload = json.loads(body)
    parsed_usgs = feeds.parse_usgs(payload)
    fetched_at = time.time()
    L["earthquakes"] = {
        "source": "USGS 2.5_day GeoJSON",
        "response_bytes": len(body),
        "fetch_latency_ms": latency_ms,
        "feed_epoch": parsed_usgs["feed_epoch"],
        "staleness_s_at_fetch": receipts.staleness_s(
            fetched_at, parsed_usgs["feed_epoch"]),
        "count": parsed_usgs["count"],
        "max_mag": parsed_usgs["max_mag"],
        "count_m45_plus": parsed_usgs["count_m45_plus"],
    }
    _write_fixture("usgs_excerpt.json", fetched_at, payload={
        "metadata": payload.get("metadata"),
        "features": (payload.get("features") or [])[:50]})

    # --- EMSC (second catalogue) + cross-source reconciliation
    payload_emsc, emsc_fetch = feeds._fetch_json(feeds.emsc_url(time.time()),
                                                 timeout=120.0)
    parsed_emsc = feeds.parse_emsc(payload_emsc)
    fetched_at = time.time()
    L["quakes_emsc"] = {
        "source": "EMSC SeismicPortal FDSN (minmag 2.5, last 24 h)",
        "response_bytes": emsc_fetch["response_bytes"],
        "fetch_latency_ms": emsc_fetch["latency_ms"],
        "feed_epoch": parsed_emsc["feed_epoch"],
        "staleness_s_at_fetch": receipts.staleness_s(
            fetched_at, parsed_emsc["feed_epoch"]),
        "count": parsed_emsc["count"],
        "max_mag": parsed_emsc["max_mag"],
        "count_m45_plus": parsed_emsc["count_m45_plus"],
    }
    _write_fixture("emsc_excerpt.json", fetched_at, payload={
        "type": payload_emsc.get("type"),
        "metadata": payload_emsc.get("metadata"),
        "features": (payload_emsc.get("features") or [])[:200]})
    cross = receipts.cross_source_quakes(parsed_usgs["points"],
                                         parsed_emsc["points"])
    out["cross_source"] = {"earthquakes_usgs_vs_emsc": cross}

    # --- Digitraffic AIS (Baltic)
    payload_ais, ais_fetch = feeds._fetch_json(feeds.AIS_URL, timeout=120.0)
    parsed_ais = feeds.parse_ais(payload_ais)
    fetched_at = time.time()
    L["vessels"] = {
        "source": "Fintraffic Digitraffic AIS /api/ais/v1/locations",
        "response_bytes": ais_fetch["response_bytes"],
        "fetch_latency_ms": ais_fetch["latency_ms"],
        "feed_epoch": parsed_ais["feed_epoch"],
        "staleness_s_at_fetch": receipts.staleness_s(
            fetched_at, parsed_ais["feed_epoch"]),
        "count": parsed_ais["count"],
        "bbox": parsed_ais["bbox"],
    }
    _write_fixture("ais_excerpt.json", fetched_at, payload={
        "type": payload_ais.get("type"),
        "dataUpdatedTime": payload_ais.get("dataUpdatedTime"),
        "features": (payload_ais.get("features") or [])[:100]})

    # --- NHC storms
    payload_nhc, nhc_fetch = feeds._fetch_json(feeds.NHC_URL)
    parsed_nhc = feeds.parse_nhc(payload_nhc)
    fetched_at = time.time()
    L["storms"] = {
        "source": "NOAA NHC CurrentStorms.json",
        "response_bytes": nhc_fetch["response_bytes"],
        "fetch_latency_ms": nhc_fetch["latency_ms"],
        "feed_epoch": parsed_nhc["feed_epoch"],
        "staleness_s_at_fetch": receipts.staleness_s(
            fetched_at, parsed_nhc["feed_epoch"]),
        "count": parsed_nhc["count"],
        "names": [p.get("name") for p in parsed_nhc["points"]],
    }
    _write_fixture("nhc_excerpt.json", fetched_at, payload=payload_nhc)

    # --- CNEOS fireballs
    payload_cneos, cneos_fetch = feeds._fetch_json(feeds.CNEOS_URL)
    parsed_cneos = feeds.parse_cneos(payload_cneos)
    fetched_at = time.time()
    L["fireballs"] = {
        "source": "NASA/JPL CNEOS fireball.api (limit 100)",
        "response_bytes": cneos_fetch["response_bytes"],
        "fetch_latency_ms": cneos_fetch["latency_ms"],
        "feed_epoch": parsed_cneos["feed_epoch"],
        "staleness_s_at_fetch": receipts.staleness_s(
            fetched_at, parsed_cneos["feed_epoch"]),
        "count": parsed_cneos["count"],
        "rows_total": parsed_cneos["rows_total"],
        "max_impact_kt": parsed_cneos["max_impact_kt"],
        "newest_event": max((p.get("date") or "") for p in parsed_cneos["points"]),
    }
    _write_fixture("cneos_excerpt.json", fetched_at, payload=payload_cneos)

    # --- NDBC buoys
    body, latency_ms, _ = feeds._fetch(feeds.NDBC_URL)
    parsed_ndbc = feeds.parse_ndbc(body.decode("utf-8", "replace"))
    fetched_at = time.time()
    L["buoys"] = {
        "source": "NOAA NDBC latest_obs.txt",
        "response_bytes": len(body),
        "fetch_latency_ms": latency_ms,
        "feed_epoch": parsed_ndbc["feed_epoch"],
        "staleness_s_at_fetch": receipts.staleness_s(
            fetched_at, parsed_ndbc["feed_epoch"]),
        "count": parsed_ndbc["count"],
    }
    ndbc_lines = body.decode("utf-8", "replace").splitlines()
    _write_fixture("ndbc_excerpt.json", fetched_at,
                   payload_text="\n".join(ndbc_lines[:120]))

    # --- WFIGS US incidents
    payload_wf, wf_fetch = feeds._fetch_json(feeds.WFIGS_URL, timeout=120.0)
    parsed_wf = feeds.parse_wfigs(payload_wf)
    L["wildfires_us"] = {
        "source": "NIFC WFIGS Incident Locations Current (ArcGIS REST)",
        "response_bytes": wf_fetch["response_bytes"],
        "fetch_latency_ms": wf_fetch["latency_ms"],
        "count": parsed_wf["count"],
        "total_acres": parsed_wf["total_acres"],
        "largest_acres": parsed_wf["largest_acres"],
        "rx_count": parsed_wf["rx_count"],
    }
    _write_fixture("wfigs_excerpt.json", time.time(), payload={
        "type": payload_wf.get("type"),
        "features": (payload_wf.get("features") or [])[:100]})

    # --- SWPC space weather (panel layer)
    kp_payload, _kf = feeds._fetch_json(feeds.SWPC_KP_URL)
    wind_payload, _wf2 = feeds._fetch_json(feeds.SWPC_WIND_URL, timeout=120.0)
    kp = feeds.parse_swpc_kp(kp_payload)
    wind = feeds.parse_swpc_wind(wind_payload)
    fetched_at = time.time()
    L["spaceweather"] = {
        "source": "NOAA SWPC planetary_k_index_1m + rtsw_wind_1m",
        "kp_latest": kp["latest_kp"],
        "kp_max_24h": kp["max_kp_24h"],
        "kp_epoch": kp["latest_epoch"],
        "wind_speed_kms": wind["speed_kms"],
        "wind_density_pcc": wind["density_pcc"],
        "wind_source": wind["source"],
        "staleness_s_at_fetch": receipts.staleness_s(fetched_at,
                                                    kp["latest_epoch"]),
    }
    _write_fixture("swpc_kp_excerpt.json", fetched_at,
                   payload=kp_payload[-60:])
    _write_fixture("swpc_wind_excerpt.json", fetched_at,
                   payload=wind_payload[:60])

    # --- FIRMS: no key in this environment -> honest off state
    firms = feeds.fetch_firms()
    L["wildfires"] = (
        {"source": "NASA FIRMS", "state": "on",
         "count": firms["count"]} if firms is not None else
        {"source": "NASA FIRMS", "state": "off",
         "reason": "No FIRMS_MAP_KEY configured; key requires the "
                   "operator's own free signup. Layer ships in the "
                   "documented off state."})

    out["claims"] = receipts.build_claims(
        L["flights"]["positioned"],
        L["satellites"]["propagated_ok"],
        L["earthquakes"]["count"],
        L["vessels"]["count"],
        L["wildfires_us"]["count"])

    (ROOT / "results" / "measurements.json").write_text(
        json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
