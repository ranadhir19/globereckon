"""Parsers against recorded real-response excerpts (fixtures/).

The fixtures are excerpts of live responses recorded 2026-11-10; each
wrapper file says so. These tests prove the parsers handle the real feed
shapes — they never claim the excerpt counts are live counts.
"""
import json
import os
from pathlib import Path

from app import feeds

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_opensky_excerpt_parses():
    fx = _load("opensky_excerpt.json")
    parsed = feeds.parse_opensky(fx["payload"])
    assert parsed["states_total"] == len(fx["payload"]["states"]) == 400
    assert parsed["feed_epoch"] == fx["payload"]["time"]
    assert 0 < parsed["positioned"] <= 400
    p = parsed["points"][0]
    assert -90 <= p["lat"] <= 90 and -180 <= p["lng"] <= 180


def test_celestrak_excerpt_propagates():
    fx = _load("celestrak_excerpt.json")
    parsed = feeds.parse_tle_propagate(fx["text"], fx["recorded_at"])
    assert parsed["elements_total"] == 30
    assert parsed["propagated_ok"] >= 28
    assert parsed["median_epoch_age_h"] is not None
    assert parsed["median_epoch_age_h"] > 0
    p = parsed["points"][0]
    assert -90 <= p["lat"] <= 90 and -180 <= p["lng"] <= 180
    assert p["alt_km"] > 100  # everything in the active catalog is in orbit


def test_usgs_excerpt_parses():
    fx = _load("usgs_excerpt.json")
    parsed = feeds.parse_usgs(fx["payload"])
    assert parsed["count"] == len(fx["payload"]["features"]) > 0
    assert parsed["feed_epoch"] == fx["payload"]["metadata"]["generated"] / 1000
    assert parsed["max_mag"] is not None


def test_firms_off_without_key(monkeypatch):
    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)
    assert feeds.fetch_firms() is None


def test_firms_csv_parse():
    text = ("latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,"
            "satellite,instrument,confidence,version,bright_ti5,frp\n"
            "28.1,-81.6,330.0,1.0,1.0,2026-11-10,0500,N,IIRS,h,3.0,367.0,12.0\n")
    parsed = feeds.parse_firms_csv(text)
    assert parsed["count"] == 1
    assert parsed["points"][0]["lat"] == 28.1


def test_tle_epoch_is_recent_for_fixture():
    fx = _load("celestrak_excerpt.json")
    first_l1 = next(ln for ln in fx["text"].splitlines()
                    if ln.startswith("1 "))
    epoch = feeds._tle_epoch(first_l1)
    assert epoch is not None
    assert abs(epoch - fx["recorded_at"]) < 14 * 86400  # within two weeks
