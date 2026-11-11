# globereckon

**A situational globe that shows its own receipts — and reconciles its
own sources against each other.**

Every demo globe repeats the same marketing numbers — ten thousand
aircraft, thousands of satellites, every earthquake live. globereckon
renders the same class of globe from public feeds, but its panels are
the point: a per-layer **receipt** measured on the fetch that drew the
map — how many objects actually came back, how old the feed's own
timestamp was, how long the fetch took, how big the response was, and
where the coverage actually is (and is not). And where two public
catalogues describe the same planet, globereckon publishes their
**disagreement**: the USGS and EMSC earthquake catalogues are matched
event by event, in the open, on every fetch.

This is a non-commercial content demo built to be filmed and written
about — a teaching artifact about how these feeds really behave. It is
**not a product**, not a data feed you may build on, and never a
navigation or safety tool.

## What it renders

Eleven layers, each with its receipt:

- **Flights** — OpenSky Network live state vectors (global). Points are
  aircraft with a reported position right now.
- **Satellites** — the CelesTrak active catalogue, propagated locally
  with the SGP4 model, with labelled sub-layers: the Starlink group
  (counted two independent ways) and the stations group, exactly as
  served. Positions are *computed* from published element sets, not
  sensed; the receipt shows the median age of those element sets,
  because a 26-hour-old element set is not "live tracking".
- **Earthquakes — USGS** — magnitude 2.5+ events, past day.
- **Earthquakes — EMSC** — a second, independent catalogue of the same
  events (EMSC-CSEM SeismicPortal, CC BY 4.0), densest in Europe and
  the Mediterranean.
- **Vessels** — live AIS positions from Fintraffic's Digitraffic open
  data. Regional by design: Finnish and Baltic waters, labelled as
  such everywhere. Source: Fintraffic / digitraffic.fi, licence
  CC 4.0 BY.
- **Ocean buoys** — NOAA NDBC moored stations, latest observation each.
- **Tropical cyclones** — NOAA NHC active storms; zero is a real
  state and is reported as zero.
- **Fireballs** — NASA/JPL CNEOS bolide events. A reviewed catalogue,
  not a stream: its newest event is usually weeks old, and its
  feed-age receipt says exactly how old.
- **US fire incidents** — NIFC WFIGS current incident points, the
  interagency dispatch record — including the prescribed burns the
  record honestly contains.
- **Wildfires (satellite detections)** — NASA FIRMS, **behind an
  optional operator key** (`FIRMS_MAP_KEY`). Without a key the layer
  renders a documented OFF state. An absent layer is a receipt too.
- **Space weather** — NOAA SWPC planetary K-index and real-time solar
  wind. A panel-only layer: a planetary index has no honest globe
  coordinates, so it draws no dots.
- **Receipts drawer** — claimed-vs-measured for the genre's marketing
  lines, the USGS-vs-EMSC cross-source reconciliation, and a
  per-layer table (objects this fetch, feed age at fetch). Clicking
  any point on the globe opens its source record.

Point altitudes on the globe are exaggerated so low objects are
visible; the UI says so on the map.

## Measured, not marketed (2026-11-10, 23:19 ET)

One live measurement run (`tools/measure.py`, full record in
`results/measurements.json`):

| Layer | Claim heard in demos | Measured here |
|---|---|---|
| Flights | "10,000+ aircraft tracked live" | **5,879 aircraft with positions** of 5,922 state vectors returned (661 on the ground); feed timestamp 9.1 s old at fetch; median position age 1 s; fetch 2,390 ms, 776 KB |
| Satellites | "2,000+ satellites tracked" | **15,882 active-catalogue element sets**, all propagated, 0 failures; median element-set age **26.0 h**; Starlink group 10,619 — exactly the Starlink-by-name count inside the active catalogue; stations group, as served, 15 sets |
| Earthquakes | "Every earthquake, live" | **USGS 36 events** (M2.5+, 24 h, max M5.6) — and **EMSC 204 events** in the same window from the second catalogue. In both: **32**. USGS only: 4. EMSC only: 172. Median magnitude disagreement on the 32 matches: **0.0** |
| Vessels | "Every ship, tracked worldwide" | **1,052 vessels** — all inside one Baltic box (lat 57.5 to 65.8, lng 16.5 to 35.8). Open AIS is regional; the rest of the world's oceans are not in any open feed |
| US fire incidents | "All US wildfires, live" | **464 current incident points**, 912,342 reported acres — of which **236 are prescribed burns**. A dispatch record, not a fire sensor |
| Fireballs | "Meteors, tracked live" | **99 located events** of the 100 most recent; largest impact energy 5.1 kt; newest event dated **2026-10-04 — 38 days before the run**. Reviewed catalogues are not streams |
| Ocean buoys | — | **802 stations** reporting a latest observation |
| Tropical cyclones | — | **1 active storm** (Pena, Central Pacific) on this run; much of the year the honest number is 0 |
| Space weather | — | Kp max over 24 h **2.33** (quiet); solar wind **527.7 km/s** from the active L1 craft |
| Wildfire detections | "Fires in real time" | **Off** — no MAP_KEY configured; the layer ships dark rather than fake |

Coverage honesty, same run: of the 5,879 plotted aircraft, the ocean
probe boxes (Mid-Atlantic, Mid-Pacific, Indian Ocean, Southern Ocean)
held **38 — 0.65%** — against 2,728 over the continental US and 654
over Europe. The flight map is dense where ADS-B ground receivers are
dense. The globe looks global; the feed is not, and the panel shows
the counts that prove it.

Counts move with time of day and feed conditions. That variance is the
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
turns the satellite-detection wildfire layer on. Offline development:
`GLOBERECKON_FIXTURES=1` serves labelled excerpts of recorded real
responses (the UI banners them as fixtures — never presented as live).

## Verify it

```bash
.venv/bin/python validate.py
```

Runs byte-compilation, the test suite (parser tests run against the
recorded-response excerpts, including a synthetic cross-source matching
test), a reference-integrity scan of the exact tree, a licence-record
check across every wired and rejected source, and a measurements
integrity stage: the claimed-vs-measured readout and the cross-source
block in `results/measurements.json` must equal the layer counts in
the same record — the README numbers are the measured numbers.
`tools/measure.py` re-runs the live measurement and refreshes
`results/measurements.json` plus the fixture excerpts.

## Data licences — the short version

Full per-source record with the terms checked on 2026-11-10 lives in
[DATA_SOURCES.md](DATA_SOURCES.md), including the sources that were
checked and **not** wired (IODA — rejected, with the reason; AISStream
and OpenAQ — key-gated, joining the FIRMS optional-key pattern). The
boundaries that matter:

- **OpenSky flight data is non-commercial research/education only.**
  Operational or commercial use needs OpenSky's separate written
  licence. This demo fetches within the anonymous quota, caches briefly
  in memory, and does not redistribute the data. Attribution: The
  OpenSky Network, https://opensky-network.org (Schäfer et al., IPSN
  2014).
- **CelesTrak** element sets are free with attribution under their
  usage policy; fetched at most hourly.
- **USGS, NOAA (SWPC, NHC, NDBC) and NASA/JPL CNEOS** information is
  US public domain / public US Government services.
- **EMSC** earthquake data is CC BY 4.0 — credit: EMSC-CSEM
  SeismicPortal, https://www.seismicportal.eu.
- **Digitraffic** vessel data is CC BY 4.0 — Source: Fintraffic /
  digitraffic.fi, licence CC 4.0 BY.
- **NIFC WFIGS** is a US federal interagency public service.
- **NASA FIRMS** data is public domain (CC0 per NASA Earthdata
  guidance); the API key is the operator's own free signup, so the
  layer ships off unless you bring one.

Do not use anything on this globe for navigation, safety, or
operational decisions.

## Licence

MIT — see [LICENSE](LICENSE). The licence covers this code, not the
feeds: each data source keeps its own terms above.
