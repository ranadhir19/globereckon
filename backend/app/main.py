"""globereckon API — a situational globe that shows its own receipts.

Run:  uvicorn app.main:app --app-dir backend --port 8077
Modes: live (default) or fixture (GLOBERECKON_FIXTURES=1) for CI/offline.
Fixture payloads are excerpts of real recorded responses, always labelled
mode="fixture" in every payload — never presented as live.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import feeds, receipts

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"
FIXTURE_MODE = os.environ.get("GLOBERECKON_FIXTURES", "") == "1"

TTL_S = {"flights": 120, "satellites": 3600, "earthquakes": 300,
         "wildfires": 600}
_cache: dict[str, tuple[float, dict]] = {}

app = FastAPI(title="globereckon", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"],
                   allow_headers=["*"])


def _fixture(name: str) -> dict:
    with open(FIXTURES / name, encoding="utf-8") as fh:
        return json.load(fh)


def _flights() -> dict:
    if FIXTURE_MODE:
        fx = _fixture("opensky_excerpt.json")
        parsed = feeds.parse_opensky(fx["payload"])
        fetched_at, fetch = fx["recorded_at"], None
        mode = "fixture"
    else:
        fetched_at = time.time()
        parsed = feeds.fetch_opensky()
        fetch, mode = parsed.pop("_fetch"), "live"
    cov = receipts.coverage_summary(parsed["points"])
    rec = {
        "source": "OpenSky Network (anonymous access)",
        "status": "on",
        "mode": mode,
        "objects_live": parsed["positioned"],
        "states_total": parsed["states_total"],
        "on_ground": parsed["on_ground"],
        "feed_epoch": parsed["feed_epoch"],
        "staleness_s": receipts.staleness_s(fetched_at, parsed["feed_epoch"]),
        "median_position_age_s": parsed["median_position_age_s"],
        "fetch": fetch,
        "cadence_note": ("Server caches 120 s. Anonymous OpenSky quota is "
                         "400 credits/day; the feed itself updates ~10 s."),
        "coverage": cov,
        "coverage_note": (
            f"Ocean probe boxes (Mid-Atlantic, Mid-Pacific, Indian Ocean, "
            f"Southern Ocean) hold {cov['ocean_box_aircraft']} of "
            f"{parsed['positioned']} positioned aircraft "
            f"({cov['ocean_share_of_all_pct']}%). The feed follows volunteer "
            f"receivers and flown routes — not the whole sky."),
    }
    return {"layer": "flights", "points": parsed["points"], "receipt": rec}


def _satellites() -> dict:
    if FIXTURE_MODE:
        fx = _fixture("celestrak_excerpt.json")
        parsed = feeds.parse_tle_propagate(fx["text"], fx["recorded_at"])
        fetched_at, fetch = fx["recorded_at"], None
        mode = "fixture"
    else:
        fetched_at = time.time()
        parsed = feeds.fetch_celestrak()
        fetch, mode = parsed.pop("_fetch"), "live"
    rec = {
        "source": "CelesTrak GP element sets (active group)",
        "status": "on",
        "mode": mode,
        "objects_live": parsed["propagated_ok"],
        "elements_total": parsed["elements_total"],
        "propagation_failed": parsed["propagation_failed"],
        "feed_epoch": None,
        "staleness_s": None,
        "median_epoch_age_h": parsed["median_epoch_age_h"],
        "fetch": fetch,
        "cadence_note": ("Element sets are republished a few times a day; "
                         "this server refetches at most once an hour, per "
                         "CelesTrak's usage policy."),
        "coverage_note": (
            "Positions on the globe are SGP4 computations from element sets "
            "whose median age is shown above — predictions from published "
            "elements, not sensor readings."),
    }
    return {"layer": "satellites", "points": parsed["points"], "receipt": rec}


def _earthquakes() -> dict:
    if FIXTURE_MODE:
        fx = _fixture("usgs_excerpt.json")
        parsed = feeds.parse_usgs(fx["payload"])
        fetched_at, fetch = fx["recorded_at"], None
        mode = "fixture"
    else:
        fetched_at = time.time()
        parsed = feeds.fetch_usgs()
        fetch, mode = parsed.pop("_fetch"), "live"
    rec = {
        "source": "USGS earthquake feed (magnitude 2.5+, last 24 h)",
        "status": "on",
        "mode": mode,
        "objects_live": parsed["count"],
        "max_mag": parsed["max_mag"],
        "count_m45_plus": parsed["count_m45_plus"],
        "feed_epoch": parsed["feed_epoch"],
        "staleness_s": receipts.staleness_s(fetched_at, parsed["feed_epoch"]),
        "fetch": fetch,
        "cadence_note": ("USGS regenerates the feed as events are processed; "
                         "reviewed events typically post within minutes."),
        "coverage_note": ("Magnitude 2.5 and above, worldwide, 24 hours. "
                          "Smaller events are excluded by the feed's design."),
    }
    return {"layer": "earthquakes", "points": parsed["points"], "receipt": rec}


def _wildfires() -> dict:
    if not FIXTURE_MODE:
        parsed = feeds.fetch_firms()
        if parsed is not None:
            fetch = parsed.pop("_fetch")
            rec = {
                "source": "NASA FIRMS (VIIRS S-NPP NRT, last 24 h, world)",
                "status": "on",
                "mode": "live",
                "objects_live": parsed["count"],
                "feed_epoch": None,
                "staleness_s": None,
                "fetch": fetch,
                "cadence_note": ("Detections are near-real-time: typically "
                                 "published within ~3 h of satellite "
                                 "overpass (documented FIRMS latency)."),
                "coverage_note": ("Only pixels a satellite saw while passing "
                                  "overhead; cloud, canopy and revisit gaps "
                                  "apply. Bright surfaces can false-alarm."),
            }
            return {"layer": "wildfires", "points": parsed["points"],
                    "receipt": rec}
    rec = {
        "source": "NASA FIRMS (VIIRS active-fire detections)",
        "status": "off",
        "mode": "fixture" if FIXTURE_MODE else "live",
        "objects_live": None,
        "feed_epoch": None,
        "staleness_s": None,
        "fetch": None,
        "cadence_note": ("Enabling requires a free FIRMS MAP_KEY from the "
                         "operator's own signup; see DATA_SOURCES.md."),
        "coverage_note": ("OFF — no FIRMS MAP_KEY is configured on this "
                          "server, so this layer shows nothing and says so. "
                          "An absent layer is a state, not a zero."),
    }
    return {"layer": "wildfires", "points": [], "receipt": rec}


_BUILDERS = {"flights": _flights, "satellites": _satellites,
             "earthquakes": _earthquakes, "wildfires": _wildfires}


def get_layer(name: str) -> dict:
    now = time.time()
    hit = _cache.get(name)
    if hit and hit[0] > now:
        return hit[1]
    try:
        payload = _BUILDERS[name]()
    except feeds.FeedError as exc:
        payload = {"layer": name, "points": [], "receipt": {
            "source": name, "status": "error", "mode": "live",
            "objects_live": None, "error": str(exc),
            "coverage_note": "Feed fetch failed; the layer reports its "
                             "error instead of drawing stale dots."}}
        _cache[name] = (now + 30, payload)
        return payload
    _cache[name] = (now + TTL_S[name], payload)
    return payload


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "mode": "fixture" if FIXTURE_MODE else "live"}


@app.get("/api/layers/{name}")
def layer(name: str) -> dict:
    if name not in _BUILDERS:
        return {"error": f"unknown layer {name!r}"}
    return get_layer(name)


@app.get("/api/layers")
def layers() -> dict:
    out = {name: get_layer(name) for name in _BUILDERS}
    claims = receipts.build_claims(
        out["flights"]["receipt"].get("objects_live"),
        out["satellites"]["receipt"].get("objects_live"),
        out["earthquakes"]["receipt"].get("objects_live"))
    return {"generated_at": time.time(),
            "mode": "fixture" if FIXTURE_MODE else "live",
            "layers": out, "claims": claims}


@app.get("/api/receipts")
def receipts_only() -> dict:
    out = {name: get_layer(name)["receipt"] for name in _BUILDERS}
    return {"generated_at": time.time(),
            "mode": "fixture" if FIXTURE_MODE else "live",
            "receipts": out,
            "claims": receipts.build_claims(
                out["flights"].get("objects_live"),
                out["satellites"].get("objects_live"),
                out["earthquakes"].get("objects_live"))}


_DIST = ROOT / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True),
              name="frontend")
