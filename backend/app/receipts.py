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


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    import math
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def cross_source_quakes(usgs_points: list[dict], emsc_points: list[dict],
                        max_dt_s: float = 120.0,
                        max_dist_km: float = 150.0) -> dict:
    """Greedy one-to-one match between two independent earthquake catalogues.

    A pair matches when origin times are within max_dt_s AND epicentres
    within max_dist_km; pairs are taken in ascending combined score so the
    closest matches lock first. This is the differentiator measurement:
    two agencies, same planet, overlapping but different catalogues.
    """
    candidates = []
    for i, u in enumerate(usgs_points):
        if u.get("time_epoch") is None:
            continue
        for j, e in enumerate(emsc_points):
            if e.get("time_epoch") is None:
                continue
            dt = abs(u["time_epoch"] - e["time_epoch"])
            if dt > max_dt_s:
                continue
            dist = haversine_km(u["lat"], u["lng"], e["lat"], e["lng"])
            if dist > max_dist_km:
                continue
            candidates.append((dt / max_dt_s + dist / max_dist_km, i, j, dt, dist))
    candidates.sort()
    used_u: set[int] = set()
    used_e: set[int] = set()
    deltas: list[float] = []
    pairs = 0
    for _score, i, j, _dt, _dist in candidates:
        if i in used_u or j in used_e:
            continue
        used_u.add(i)
        used_e.add(j)
        pairs += 1
        um, em = usgs_points[i].get("mag"), emsc_points[j].get("mag")
        if isinstance(um, (int, float)) and isinstance(em, (int, float)):
            deltas.append(abs(float(um) - float(em)))
    deltas.sort()
    return {
        "usgs_total": len(usgs_points),
        "emsc_total": len(emsc_points),
        "matched": pairs,
        "usgs_only": len(usgs_points) - pairs,
        "emsc_only": len(emsc_points) - pairs,
        "median_abs_mag_delta": (round(deltas[len(deltas) // 2], 2)
                                 if deltas else None),
        "match_rule": (f"origin time within {int(max_dt_s)} s and epicentre "
                       f"within {int(max_dist_km)} km, greedy closest-first"),
    }


def build_claims(flight_count: int | None, sat_count: int | None,
                 quake_count: int | None,
                 vessel_count: int | None = None,
                 us_fire_count: int | None = None) -> list[dict]:
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
    if vessel_count is not None:
        claims.append({
            "claim": "Every ship, tracked worldwide",
            "measured": vessel_count,
            "reading": ("This is one regional open AIS feed — Finnish and "
                        "Baltic waters, published by Fintraffic under "
                        "CC BY 4.0. Global AIS exists, but it is not open; "
                        "the honest open map has a coastline-shaped hole "
                        "everywhere else."),
        })
    if us_fire_count is not None:
        claims.append({
            "claim": "All US wildfires, live",
            "measured": us_fire_count,
            "reading": ("This is the interagency incident record (WFIGS): "
                        "dispatch points, including prescribed burns, "
                        "updated when incident staff publish — a records "
                        "system keeping pace with fires, not a sensor "
                        "watching them."),
        })
    return claims
