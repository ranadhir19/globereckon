"""Round-2 parsers against recorded real-response excerpts (fixtures/).

Every fixture here was recorded by tools/measure.py on 2026-11-10 from
the live public feed named in DATA_SOURCES.md. Tests prove parser shape
handling only; live counts live in results/measurements.json.
"""
import json
from pathlib import Path

from app import feeds, receipts

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_cneos_excerpt_parses_with_signed_coordinates():
    fx = _load("cneos_excerpt.json")
    parsed = feeds.parse_cneos(fx["payload"])
    assert parsed["rows_total"] == len(fx["payload"]["data"]) == 100
    assert 0 < parsed["count"] <= 100
    # First recorded row: 41.8 S, 173.1 W -> negative lat and lng.
    first = next(p for p in parsed["points"] if p["date"] == "2026-10-04 03:14:45")
    assert first["lat"] == -41.8 and first["lng"] == -173.1
    assert first["impact_kt"] == 0.18
    assert parsed["max_impact_kt"] is not None


def test_swpc_excerpts_parse():
    kp = feeds.parse_swpc_kp(_load("swpc_kp_excerpt.json")["payload"])
    assert kp["latest_kp"] is not None
    assert kp["latest_epoch"] is not None
    assert kp["max_kp_24h"] is not None
    wind = feeds.parse_swpc_wind(_load("swpc_wind_excerpt.json")["payload"])
    assert wind["entries"] > 0
    if wind["speed_kms"] is not None:
        assert 200 < wind["speed_kms"] < 1200  # plausible solar wind, km/s


def test_nhc_excerpt_parses():
    fx = _load("nhc_excerpt.json")
    parsed = feeds.parse_nhc(fx["payload"])
    assert parsed["count"] == len(fx["payload"]["activeStorms"])
    if parsed["count"]:
        p = parsed["points"][0]
        assert -90 <= p["lat"] <= 90 and -180 <= p["lng"] <= 180
        assert p["name"]


def test_emsc_excerpt_parses():
    fx = _load("emsc_excerpt.json")
    parsed = feeds.parse_emsc(fx["payload"])
    assert parsed["count"] == len(fx["payload"]["features"]) > 0
    p = parsed["points"][0]
    assert p["time_epoch"] is not None and p["mag"] is not None
    assert parsed["feed_epoch"] is not None


def test_ais_excerpt_parses_and_stays_in_the_baltic():
    fx = _load("ais_excerpt.json")
    parsed = feeds.parse_ais(fx["payload"])
    assert parsed["count"] == len(fx["payload"]["features"]) == 100
    bb = parsed["bbox"]
    # The regional honesty claim, enforced: excerpt points sit in the
    # Finnish/Baltic box, nowhere near a global spread.
    assert 53 < bb["lat_min"] and bb["lat_max"] < 70
    assert 10 < bb["lng_min"] and bb["lng_max"] < 42


def test_ndbc_excerpt_parses():
    fx = _load("ndbc_excerpt.json")
    parsed = feeds.parse_ndbc(fx["payload_text"])
    assert parsed["count"] > 50
    assert parsed["feed_epoch"] is not None
    assert all(-90 <= p["lat"] <= 90 for p in parsed["points"])


def test_wfigs_excerpt_parses():
    fx = _load("wfigs_excerpt.json")
    parsed = feeds.parse_wfigs(fx["payload"])
    assert parsed["count"] == len(fx["payload"]["features"]) == 100
    assert parsed["total_acres"] >= 0
    assert 0 <= parsed["rx_count"] <= 100


def test_stations_subgroup_propagates():
    fx = _load("celestrak_stations_excerpt.json")
    parsed = feeds.parse_tle_propagate(fx["text"], fx["recorded_at"])
    assert parsed["elements_total"] == 15
    assert parsed["propagated_ok"] == 15
    names = {p["label"] for p in parsed["points"]}
    assert any("ISS" in n for n in names)


def test_cross_source_matching_synthetic():
    usgs = [
        {"lat": 35.0, "lng": 23.0, "mag": 3.0, "time_epoch": 1000.0},
        {"lat": -10.0, "lng": 120.0, "mag": 5.0, "time_epoch": 2000.0},
        {"lat": 60.0, "lng": -150.0, "mag": 2.8, "time_epoch": 3000.0},
    ]
    emsc = [
        {"lat": 35.01, "lng": 23.01, "mag": 3.2, "time_epoch": 1030.0},
        {"lat": -10.02, "lng": 119.98, "mag": 4.9, "time_epoch": 1950.0},
        {"lat": 0.0, "lng": 0.0, "mag": 4.0, "time_epoch": 5000.0},
    ]
    x = receipts.cross_source_quakes(usgs, emsc)
    assert x["matched"] == 2
    assert x["usgs_only"] == 1 and x["emsc_only"] == 1
    assert x["median_abs_mag_delta"] == 0.2


def test_cross_source_never_double_matches():
    usgs = [{"lat": 35.0, "lng": 23.0, "mag": 3.0, "time_epoch": 1000.0}]
    emsc = [
        {"lat": 35.0, "lng": 23.0, "mag": 3.0, "time_epoch": 1005.0},
        {"lat": 35.0, "lng": 23.0, "mag": 3.1, "time_epoch": 1010.0},
    ]
    x = receipts.cross_source_quakes(usgs, emsc)
    assert x["matched"] == 1 and x["emsc_only"] == 1


def test_claims_round2_carry_measured_numbers():
    claims = receipts.build_claims(100, 200, 30, 1052, 464)
    by_claim = {c["claim"]: c["measured"] for c in claims}
    assert by_claim["Every ship, tracked worldwide"] == 1052
    assert by_claim["All US wildfires, live"] == 464
    # Backwards-compatible: three-arg call still yields the original three.
    assert len(receipts.build_claims(1, 2, 3)) == 3
