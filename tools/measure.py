#!/usr/bin/env python3
"""Live measurement run for globereckon.

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


def main() -> int:
    out: dict = {"measured_at_unix": time.time(), "layers": {}}

    # --- OpenSky: one anonymous global call (4-credit class; quota 400/day)
    body, latency_ms, _ = feeds._fetch(feeds.OPENSKY_URL)
    payload = json.loads(body)
    parsed = feeds.parse_opensky(payload)
    fetched_at = time.time()
    cov = receipts.coverage_summary(parsed["points"])
    out["layers"]["flights"] = {
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
    excerpt = {"time": payload.get("time"),
               "states": (payload.get("states") or [])[:400]}
    (ROOT / "fixtures" / "opensky_excerpt.json").write_text(json.dumps({
        "recorded_at": fetched_at,
        "note": ("Excerpt of a real recorded OpenSky response: the first "
                 "400 state vectors only. Full-response counts are in "
                 "results/measurements.json. Never presented as live."),
        "payload": excerpt}), encoding="utf-8")

    # --- CelesTrak: active group TLE, propagated now
    body, latency_ms, _ = feeds._fetch(feeds.CELESTRAK_URL)
    text = body.decode("utf-8", "replace")
    fetched_at = time.time()
    parsed = feeds.parse_tle_propagate(text, fetched_at)
    out["layers"]["satellites"] = {
        "source": "CelesTrak GP, GROUP=active, FORMAT=tle",
        "response_bytes": len(body),
        "fetch_latency_ms": latency_ms,
        "elements_total": parsed["elements_total"],
        "propagated_ok": parsed["propagated_ok"],
        "propagation_failed": parsed["propagation_failed"],
        "median_epoch_age_h": parsed["median_epoch_age_h"],
    }
    lines = text.splitlines()
    (ROOT / "fixtures" / "celestrak_excerpt.json").write_text(json.dumps({
        "recorded_at": fetched_at,
        "note": ("Excerpt of a real recorded CelesTrak response: the first "
                 "30 element sets only. Full-catalog counts are in "
                 "results/measurements.json. Never presented as live."),
        "text": "\n".join(lines[:90])}), encoding="utf-8")

    # --- USGS
    body, latency_ms, _ = feeds._fetch(feeds.USGS_URL)
    payload = json.loads(body)
    parsed = feeds.parse_usgs(payload)
    fetched_at = time.time()
    out["layers"]["earthquakes"] = {
        "source": "USGS 2.5_day GeoJSON",
        "response_bytes": len(body),
        "fetch_latency_ms": latency_ms,
        "feed_epoch": parsed["feed_epoch"],
        "staleness_s_at_fetch": receipts.staleness_s(fetched_at,
                                                    parsed["feed_epoch"]),
        "count": parsed["count"],
        "max_mag": parsed["max_mag"],
        "count_m45_plus": parsed["count_m45_plus"],
    }
    excerpt = {"metadata": payload.get("metadata"),
               "features": (payload.get("features") or [])[:50]}
    (ROOT / "fixtures" / "usgs_excerpt.json").write_text(json.dumps({
        "recorded_at": fetched_at,
        "note": ("Excerpt of a real recorded USGS response: up to the "
                 "first 50 features. Full counts are in "
                 "results/measurements.json. Never presented as live."),
        "payload": excerpt}), encoding="utf-8")

    # --- FIRMS: no key in this environment -> honest off state
    firms = feeds.fetch_firms()
    out["layers"]["wildfires"] = (
        {"source": "NASA FIRMS", "state": "on",
         "count": firms["count"]} if firms is not None else
        {"source": "NASA FIRMS", "state": "off",
         "reason": "No FIRMS_MAP_KEY configured; key requires the "
                   "operator's own free signup. Layer ships in the "
                   "documented off state."})

    out["claims"] = receipts.build_claims(
        out["layers"]["flights"]["positioned"],
        out["layers"]["satellites"]["propagated_ok"],
        out["layers"]["earthquakes"]["count"])

    (ROOT / "results" / "measurements.json").write_text(
        json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
