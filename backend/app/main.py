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
         "wildfires": 600, "quakes_emsc": 300, "vessels": 120,
         "storms": 600, "fireballs": 3600, "buoys": 600,
         "wildfires_us": 300, "spaceweather": 300}
_cache: dict[str, tuple[float, dict]] = {}

app = FastAPI(title="globereckon", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"],
                   allow_headers=["*"])


def _fixture(name: str) -> dict:
    with open(FIXTURES / name, encoding="utf-8") as fh:
        return json.load(fh)


def _fixture_text(name: str) -> str:
    with open(FIXTURES / name, encoding="utf-8") as fh:
        return fh.read()


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
        stations = None
        try:
            sfx = _fixture("celestrak_stations_excerpt.json")
            stations = feeds.parse_tle_propagate(sfx["text"], sfx["recorded_at"])
        except FileNotFoundError:
            stations = None
        starlink_group_total = None
    else:
        fetched_at = time.time()
        parsed = feeds.fetch_celestrak()
        fetch, mode = parsed.pop("_fetch"), "live"
        try:
            stations = feeds.fetch_tle_group("stations")
            stations.pop("_fetch", None)
        except feeds.FeedError:
            stations = None
        try:
            starlink_group = feeds.fetch_tle_group("starlink")
            starlink_group_total = starlink_group["elements_total"]
        except feeds.FeedError:
            starlink_group_total = None
    starlink_named = sum(1 for p in parsed["points"]
                         if (p.get("label") or "").upper().startswith("STARLINK"))
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
        "sublayers": {
            "active_total": parsed["elements_total"],
            "starlink_in_active_by_name": starlink_named,
            "starlink_group_elements": starlink_group_total,
            "stations_group_elements": (stations["elements_total"]
                                        if stations else None),
            "stations_group_propagated": (stations["propagated_ok"]
                                          if stations else None),
        },
        "coverage_note": (
            "Positions on the globe are SGP4 computations from element sets "
            "whose median age is shown above — predictions from published "
            "elements, not sensor readings. Sub-layers: the stations group "
            "and the Starlink group are separate CelesTrak views of the "
            "same catalogue (they overlap the active total; they are not "
            "additive). Starlink-in-active is counted by name prefix."),
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
                          "Smaller events are excluded by the feed's design. "
                          "Compare with the EMSC layer: same planet, second "
                          "catalogue — the receipts drawer reconciles them."),
    }
    return {"layer": "earthquakes", "points": parsed["points"], "receipt": rec}


def _quakes_emsc() -> dict:
    if FIXTURE_MODE:
        fx = _fixture("emsc_excerpt.json")
        parsed = feeds.parse_emsc(fx["payload"])
        fetched_at, fetch = fx["recorded_at"], None
        mode = "fixture"
    else:
        fetched_at = time.time()
        parsed = feeds.fetch_emsc()
        fetch, mode = parsed.pop("_fetch"), "live"
    rec = {
        "source": "EMSC SeismicPortal FDSN (magnitude 2.5+, last 24 h)",
        "status": "on",
        "mode": mode,
        "objects_live": parsed["count"],
        "max_mag": parsed["max_mag"],
        "count_m45_plus": parsed["count_m45_plus"],
        "feed_epoch": parsed["feed_epoch"],
        "staleness_s": receipts.staleness_s(fetched_at, parsed["feed_epoch"]),
        "fetch": fetch,
        "cadence_note": ("EMSC-RTS aggregates dozens of national agencies "
                         "in near-real time; events are revised as agencies "
                         "update solutions."),
        "coverage_note": ("Second, independent catalogue of the same "
                          "planet (CC BY 4.0, EMSC-CSEM SeismicPortal). "
                          "Densest in Europe and the Mediterranean. The "
                          "receipts drawer matches it against USGS event "
                          "by event — agreement is measured, not assumed."),
    }
    return {"layer": "quakes_emsc", "points": parsed["points"], "receipt": rec}


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


def _wildfires_us() -> dict:
    if FIXTURE_MODE:
        fx = _fixture("wfigs_excerpt.json")
        parsed = feeds.parse_wfigs(fx["payload"])
        fetched_at, fetch = fx["recorded_at"], None
        mode = "fixture"
    else:
        fetched_at = time.time()
        parsed = feeds.fetch_wfigs()
        fetch, mode = parsed.pop("_fetch"), "live"
    rec = {
        "source": "NIFC WFIGS incident locations (current, US)",
        "status": "on",
        "mode": mode,
        "objects_live": parsed["count"],
        "total_acres": parsed["total_acres"],
        "largest_acres": parsed["largest_acres"],
        "rx_count": parsed["rx_count"],
        "feed_epoch": None,
        "staleness_s": None,
        "fetch": fetch,
        "cadence_note": ("The interagency record updates when incident "
                         "staff publish revisions — minutes to hours, "
                         "driven by people, not sensors."),
        "coverage_note": (
            f"US incident dispatch points from the IRWIN record. "
            f"{parsed['rx_count']} of the current points are prescribed "
            f"burns (names carrying RX) — the 'current incidents' layer is "
            f"a records system, not a wall of uncontrolled fire. Compare "
            f"with the FIRMS layer: detections vs dispatches."),
    }
    return {"layer": "wildfires_us", "points": parsed["points"], "receipt": rec}


def _vessels() -> dict:
    if FIXTURE_MODE:
        fx = _fixture("ais_excerpt.json")
        parsed = feeds.parse_ais(fx["payload"])
        fetched_at, fetch = fx["recorded_at"], None
        mode = "fixture"
    else:
        fetched_at = time.time()
        parsed = feeds.fetch_ais()
        fetch, mode = parsed.pop("_fetch"), "live"
    bb = parsed.get("bbox") or {}
    rec = {
        "source": "Fintraffic Digitraffic AIS (Finnish/Baltic waters)",
        "status": "on",
        "mode": mode,
        "objects_live": parsed["count"],
        "feed_epoch": parsed["feed_epoch"],
        "staleness_s": receipts.staleness_s(fetched_at, parsed["feed_epoch"]),
        "fetch": fetch,
        "bbox": parsed.get("bbox"),
        "cadence_note": ("Shore AIS receivers report continuously; this "
                         "server caches 120 s. Source: Fintraffic / "
                         "digitraffic.fi, licence CC 4.0 BY."),
        "coverage_note": (
            "Regional by design: this open feed covers Finnish and Baltic "
            "waters only"
            + (f" (this fetch spans lat {bb.get('lat_min')} to "
               f"{bb.get('lat_max')}, lng {bb.get('lng_min')} to "
               f"{bb.get('lng_max')})" if bb else "")
            + ". Global commercial AIS is not open data; the honest open "
              "globe has ships exactly where a public authority publishes "
              "them, and nowhere else."),
    }
    return {"layer": "vessels", "points": parsed["points"], "receipt": rec}


def _storms() -> dict:
    if FIXTURE_MODE:
        fx = _fixture("nhc_excerpt.json")
        parsed = feeds.parse_nhc(fx["payload"])
        fetched_at, fetch = fx["recorded_at"], None
        mode = "fixture"
    else:
        fetched_at = time.time()
        parsed = feeds.fetch_nhc()
        fetch, mode = parsed.pop("_fetch"), "live"
    rec = {
        "source": "NOAA National Hurricane Center (CurrentStorms)",
        "status": "on",
        "mode": mode,
        "objects_live": parsed["count"],
        "feed_epoch": parsed["feed_epoch"],
        "staleness_s": receipts.staleness_s(fetched_at, parsed["feed_epoch"]),
        "fetch": fetch,
        "cadence_note": ("Advisories issue on a synoptic cycle (typically "
                         "every 6 h, with intermediates); the feed's own "
                         "lastUpdate is the receipt."),
        "coverage_note": (
            "Atlantic and eastern/central Pacific tropical cyclones with "
            "active advisories. Zero is a real state for much of the "
            "year — the layer reports 0 storms, it does not invent "
            "weather. Forecast cones are published as KMZ links in each "
            "storm's detail, not redrawn here."),
    }
    return {"layer": "storms", "points": parsed["points"], "receipt": rec}


def _fireballs() -> dict:
    if FIXTURE_MODE:
        fx = _fixture("cneos_excerpt.json")
        parsed = feeds.parse_cneos(fx["payload"])
        fetched_at, fetch = fx["recorded_at"], None
        mode = "fixture"
    else:
        fetched_at = time.time()
        parsed = feeds.fetch_cneos()
        fetch, mode = parsed.pop("_fetch"), "live"
    rec = {
        "source": "NASA/JPL CNEOS fireball database (most recent 100)",
        "status": "on",
        "mode": mode,
        "objects_live": parsed["count"],
        "rows_total": parsed["rows_total"],
        "max_impact_kt": parsed["max_impact_kt"],
        "feed_epoch": parsed["feed_epoch"],
        "staleness_s": receipts.staleness_s(fetched_at, parsed["feed_epoch"]),
        "fetch": fetch,
        "cadence_note": ("An event catalogue, not a stream: US Government "
                         "sensor events are published after review, so the "
                         "newest event is typically weeks old. The feed "
                         "age receipt on this layer measures that honestly."),
        "coverage_note": ("Events with a reported location only; energy "
                          "is the computed total impact energy in kilotons. "
                          "Detection follows sensor coverage and reporting, "
                          "not meteor frequency."),
    }
    return {"layer": "fireballs", "points": parsed["points"], "receipt": rec}


def _buoys() -> dict:
    if FIXTURE_MODE:
        fx = _fixture("ndbc_excerpt.json")
        parsed = feeds.parse_ndbc(fx["payload_text"])
        fetched_at, fetch = fx["recorded_at"], None
        mode = "fixture"
    else:
        fetched_at = time.time()
        parsed = feeds.fetch_ndbc()
        fetch, mode = parsed.pop("_fetch"), "live"
    rec = {
        "source": "NOAA NDBC moored buoys (latest observations)",
        "status": "on",
        "mode": mode,
        "objects_live": parsed["count"],
        "feed_epoch": parsed["feed_epoch"],
        "staleness_s": receipts.staleness_s(fetched_at, parsed["feed_epoch"]),
        "fetch": fetch,
        "cadence_note": ("Buoys report roughly hourly; the latest_obs file "
                         "is the freshest observation per station."),
        "coverage_note": ("Fixed moorings — mostly US coastal waters plus "
                          "partner stations. A buoy is a point that never "
                          "moves; gaps are oceans nobody moored."),
    }
    return {"layer": "buoys", "points": parsed["points"], "receipt": rec}


def _spaceweather() -> dict:
    if FIXTURE_MODE:
        kfx = _fixture("swpc_kp_excerpt.json")
        wfx = _fixture("swpc_wind_excerpt.json")
        kp = feeds.parse_swpc_kp(kfx["payload"])
        wind = feeds.parse_swpc_wind(wfx["payload"])
        fetched_at, fetch = kfx["recorded_at"], None
        mode = "fixture"
    else:
        fetched_at = time.time()
        parsed = feeds.fetch_spaceweather()
        kp, wind = parsed["kp"], parsed["wind"]
        fetch, mode = parsed.pop("_fetch"), "live"
    rec = {
        "source": "NOAA SWPC (planetary K-index + real-time solar wind)",
        "status": "on",
        "mode": mode,
        "objects_live": None,
        "panel_only": True,
        "kp_latest": kp["latest_kp"],
        "kp_max_24h": kp["max_kp_24h"],
        "kp_epoch": kp["latest_epoch"],
        "wind_speed_kms": wind["speed_kms"],
        "wind_density_pcc": wind["density_pcc"],
        "wind_source": wind["source"],
        "feed_epoch": kp["latest_epoch"],
        "staleness_s": receipts.staleness_s(fetched_at, kp["latest_epoch"]),
        "fetch": fetch,
        "cadence_note": ("K-index estimates publish every minute; solar "
                         "wind is measured at L1 by the active spacecraft "
                         "named in the receipt and reaches Earth roughly "
                         "30-60 minutes later."),
        "coverage_note": ("No globe points: space weather is a planetary "
                          "index, not a place. Drawing dots for it would "
                          "be decoration, so this layer lives in the panel "
                          "where its numbers belong. Kp 5 or above is "
                          "geomagnetic storm level."),
    }
    return {"layer": "spaceweather", "points": [], "receipt": rec}


_BUILDERS = {"flights": _flights, "satellites": _satellites,
             "earthquakes": _earthquakes, "quakes_emsc": _quakes_emsc,
             "wildfires": _wildfires, "wildfires_us": _wildfires_us,
             "vessels": _vessels, "storms": _storms,
             "fireballs": _fireballs, "buoys": _buoys,
             "spaceweather": _spaceweather}


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


def _cross(out: dict) -> dict | None:
    try:
        return receipts.cross_source_quakes(
            out["earthquakes"]["points"], out["quakes_emsc"]["points"])
    except Exception:
        return None


def _claims(out: dict) -> list:
    return receipts.build_claims(
        out["flights"]["receipt"].get("objects_live"),
        out["satellites"]["receipt"].get("objects_live"),
        out["earthquakes"]["receipt"].get("objects_live"),
        out["vessels"]["receipt"].get("objects_live"),
        out["wildfires_us"]["receipt"].get("objects_live"))


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
    return {"generated_at": time.time(),
            "mode": "fixture" if FIXTURE_MODE else "live",
            "layers": out, "claims": _claims(out),
            "cross_source": {"earthquakes_usgs_vs_emsc": _cross(out)}}


@app.get("/api/receipts")
def receipts_only() -> dict:
    out = {name: get_layer(name) for name in _BUILDERS}
    return {"generated_at": time.time(),
            "mode": "fixture" if FIXTURE_MODE else "live",
            "receipts": {name: out[name]["receipt"] for name in _BUILDERS},
            "claims": _claims(out),
            "cross_source": {"earthquakes_usgs_vs_emsc": _cross(out)}}


_DIST = ROOT / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True),
              name="frontend")
