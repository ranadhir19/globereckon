"""The receipts engine — globereckon's added value.

A situational globe is easy to draw and easy to lie about. This module
measures what each feed actually delivered on this fetch: how many objects,
how old the feed's own timestamps are, how long the fetch took, and where
the aircraft feed is thin (fixed probe boxes over open ocean vs continents).
All numbers are computed from the payload in hand — nothing is hardcoded.
"""

from __future__ import annotations

# Fixed probe rectangles: (name, lat_min, lat_max, lng_min, lng_max, kind)
PROBE_BOXES: list[tuple[str, float, float, float, float, str]] = [
    ("Continental US", 25.0, 49.0, -125.0, -66.0, "land"),
    ("Europe", 36.0, 70.0, -11.0, 40.0, "land"),
    ("Mid-Atlantic", -5.0, 35.0, -42.0, -18.0, "ocean"),
    ("Mid-Pacific", -5.0, 28.0, -178.0, -145.0, "ocean"),
    ("Indian Ocean", -28.0, 5.0, 58.0, 95.0, "ocean"),
    ("Southern Ocean", -63.0, -42.0, -180.0, 180.0, "ocean"),
]


def box_counts(points: list[dict]) -> dict[str, int]:
    counts = {name: 0 for name, *_ in PROBE_BOXES}
    for p in points:
        lat, lng = p["lat"], p["lng"]
        for name, la0, la1, lo0, lo1, _kind in PROBE_BOXES:
            if la0 <= lat <= la1 and lo0 <= lng <= lo1:
                counts[name] += 1
    return counts


def coverage_summary(points: list[dict]) -> dict:
    counts = box_counts(points)
    ocean = sum(counts[n] for n, *_, k in PROBE_BOXES if k == "ocean")
    land = sum(counts[n] for n, *_, k in PROBE_BOXES if k == "land")
    total = len(points)
    return {
        "probe_boxes": counts,
        "ocean_box_aircraft": ocean,
        "land_box_aircraft": land,
        "ocean_share_of_all_pct": round(100.0 * ocean / total, 2) if total else None,
    }


def staleness_s(fetched_at: float, feed_epoch: float | None) -> float | None:
    if feed_epoch is None:
        return None
    return round(fetched_at - feed_epoch, 1)


def build_claims(flight_count: int | None, sat_count: int | None,
                 quake_count: int | None) -> list[dict]:
    """Claimed-vs-measured readout. Claims are the genre's marketing lines
    (from the reference reel's genre, paraphrased as claims, not copied);
    measured values are this server's live counts."""
    claims = []
    if flight_count is not None:
        claims.append({
            "claim": "10,000+ aircraft tracked live",
            "measured": flight_count,
            "reading": ("The count is a property of the free public feed and "
                        "the time of day, not of any dashboard's engineering. "
                        "Our measured count right now is the number above."),
        })
    if sat_count is not None:
        claims.append({
            "claim": "2,000+ satellites tracked",
            "measured": sat_count,
            "reading": ("The public active catalogue holds far more objects "
                        "than the marketing number; positions are computed "
                        "from published element sets, not 'tracked' by the "
                        "dashboard."),
        })
    if quake_count is not None:
        claims.append({
            "claim": "Every earthquake, live",
            "measured": quake_count,
            "reading": ("This is the USGS magnitude-2.5+ feed for the last "
                        "24 hours: reviewed, delayed by minutes, and blind "
                        "to smaller events by design."),
        })
    return claims
