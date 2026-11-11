# globereckon

**A situational globe that shows its own receipts.**

Every demo globe repeats the same marketing numbers — ten thousand
aircraft, thousands of satellites, every earthquake live. globereckon
renders the same class of globe from public feeds, but its side panel is
the point: a per-layer **receipt** measured on the fetch that drew the
map — how many objects actually came back, how old the feed's own
timestamp was, how long the fetch took, how big the response was, and
where the coverage actually is (and is not). Claimed vs measured, side by
side, from the demo's own numbers.

This is a non-commercial content demo built to be filmed and written
about — a teaching artifact about how these feeds really behave. It is
**not a product**, not a data feed you may build on, and never a
navigation or safety tool.

## What it renders

- **Flights** — OpenSky Network live state vectors (global). Points are
  aircraft with a reported position right now.
- **Satellites** — the CelesTrak active catalogue, propagated locally
  with the SGP4 model. Positions are *computed* from published element
  sets, not sensed; the receipt shows the median age of those element
  sets, because a 26-hour-old element set is not "live tracking".
- **Earthquakes** — USGS magnitude 2.5+ events, past day.
- **Wildfires** — NASA FIRMS active-fire detections, **behind an
  optional operator key** (`FIRMS_MAP_KEY`). Without a key the layer
  renders a documented OFF state. An absent layer is a receipt too.
- **Receipts panel** — objects-live count, feed-timestamp age, fetch
  latency and size, refresh cadence, a coverage note per layer, a
  probe-box table for flights (how many of those aircraft are over
  oceans, where ground receivers are sparse), and a claimed-vs-measured
  readout.

Point altitudes on the globe are exaggerated so low objects are visible;
the UI says so on the map.

## Measured, not marketed (2026-11-10, 22:51 ET)

One live measurement run (`tools/measure.py`, full record in
`results/measurements.json`):

| Layer | Claim heard in demos | Measured here |
|---|---|---|
| Flights | "10,000+ aircraft tracked live" | **6,210 aircraft with positions** of 6,259 state vectors returned (757 on the ground); feed timestamp 9.6 s old at fetch; median position age 1 s; fetch 2,657 ms, 821 KB |
| Satellites | "2,000+ satellites tracked" | **15,882 active-catalogue element sets**, all 15,882 propagated, 0 failures; median element-set age **25.6 h**; fetch 3,013 ms, 2.67 MB |
| Earthquakes | "Every earthquake, live" | **35 events** in the USGS 2.5+ day feed (the feed's own count agreed), max M5.6, 15 at M4.5+; feed generated 28.1 s before the fetch |
| Wildfires | "Fires in real time" | **Off** — no MAP_KEY configured; the layer ships dark rather than fake |

Coverage honesty, same run: of the 6,210 plotted aircraft, the ocean
probe boxes (Mid-Atlantic, Mid-Pacific, Indian Ocean, Southern Ocean)
held **58 — 0.93%** — against 3,139 over the continental US and 548 over
Europe. The flight map is dense where ADS-B ground receivers are dense,
and the Indian Ocean box held exactly **0**. The globe looks global;
the feed is not, and the panel shows the counts that prove it.

Counts move with time of day and feed conditions — a second live fetch
minutes later returned 6,186 positioned aircraft. That variance is the
lesson: an object count is a property of the feed and the hour, not of
the dashboard.

## Run it

Backend (Python 3.11+):

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
.venv/bin/python -m uvicorn app.main:app --app-dir backend --port 8077
```

Frontend (Node 18+):

```bash
cd frontend && npm install && npm run build && cd ..
```

Then open http://127.0.0.1:8077 — the backend serves the built frontend
and the API together. For frontend development, `npm run dev` proxies
`/api` to the backend.

Optional: `FIRMS_MAP_KEY=<your free key>` in the backend environment
turns the wildfire layer on. Offline development:
`GLOBERECKON_FIXTURES=1` serves labelled excerpts of recorded real
responses (the UI banners them as fixtures — never presented as live).

## Verify it

```bash
.venv/bin/python validate.py
```

Runs byte-compilation, the test suite (parser tests run against the
recorded-response excerpts), a reference-integrity scan of the exact
tree, and a licence-record check.
`tools/measure.py` re-runs the live measurement and refreshes
`results/measurements.json` plus the fixture excerpts.

## Data licences — the short version

Full per-source record with the terms checked on 2026-11-10 lives in
[DATA_SOURCES.md](DATA_SOURCES.md). The boundary that matters:

- **OpenSky flight data is non-commercial research/education only.**
  Operational or commercial use needs OpenSky's separate written
  licence. This demo fetches within the anonymous quota, caches briefly
  in memory, and does not redistribute the data. Attribution: The
  OpenSky Network, https://opensky-network.org (Schäfer et al., IPSN
  2014).
- **CelesTrak** element sets are free with attribution under their usage
  policy; fetched at most hourly.
- **USGS** information is US public domain.
- **NASA FIRMS** data is public domain (CC0 per NASA Earthdata
  guidance); the API key is the operator's own free signup, so the layer
  ships off unless you bring one.

Do not use anything on this globe for navigation, safety, or operational
decisions.

## Licence

MIT — see [LICENSE](LICENSE). The licence covers this code, not the
feeds: each data source keeps its own terms above.
