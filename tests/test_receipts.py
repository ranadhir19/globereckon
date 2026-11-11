"""Receipts math: probe boxes, ocean share, staleness, claims."""
from app import receipts


def _pts(*coords):
    return [{"lat": la, "lng": lo, "alt_km": 0.0, "label": ""} for la, lo in coords]


def test_box_counts_hit_the_right_boxes():
    pts = _pts((39.0, -98.0),    # Continental US
               (15.0, -30.0),    # Mid-Atlantic
               (-50.0, 10.0),    # Southern Ocean
               (0.0, 130.0))     # no probe box (Indonesia seas)
    counts = receipts.box_counts(pts)
    assert counts["Continental US"] == 1
    assert counts["Mid-Atlantic"] == 1
    assert counts["Southern Ocean"] == 1
    assert counts["Europe"] == 0
    assert sum(counts.values()) == 3


def test_coverage_summary_ocean_share():
    cov = receipts.coverage_summary(_pts((39.0, -98.0), (15.0, -30.0)))
    assert cov["ocean_box_aircraft"] == 1
    assert cov["land_box_aircraft"] == 1
    assert cov["ocean_share_of_all_pct"] == 50.0


def test_staleness():
    assert receipts.staleness_s(1000.0, 940.0) == 60.0
    assert receipts.staleness_s(1000.0, None) is None


def test_claims_carry_the_measured_numbers():
    claims = receipts.build_claims(6210, 15882, 35)
    by_claim = {c["claim"]: c["measured"] for c in claims}
    assert by_claim["10,000+ aircraft tracked live"] == 6210
    assert by_claim["2,000+ satellites tracked"] == 15882
    assert by_claim["Every earthquake, live"] == 35
    assert receipts.build_claims(None, None, None) == []
