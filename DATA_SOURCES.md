# Data sources and licence record — globereckon

Every feed in this demo was checked against its provider's own published
terms before the layer was built. Verified 2026-11-10 (America/New_York).
This file is the per-source record required by the project's compliance
gate; validate.py fails if it goes missing.

## 1. Flights — OpenSky Network

- **Dataset/endpoint:** live state vectors, `GET https://opensky-network.org/api/states/all` (anonymous tier).
- **Terms:** https://opensky-network.org/about/terms-of-use and
  https://opensky-network.org/data/termsOfUse — academic/research terms.
  The terms license the data "solely for non-profit research and
  non-profit education purposes"; "Operational use of OpenSky data, data
  processing and data display tools is not subject of this Agreement" and
  requires a separate written licence. Even academic users must agree the
  data and derived products "will not be used for commercial purposes".
- **Our use:** permitted as a non-commercial research/educational content
  artifact. The demo fetches on demand and caches in memory for 120 s;
  it does **not** store, redistribute, or sell OpenSky data; the recorded
  fixture in `fixtures/` is a 400-vector excerpt kept for parser tests
  and labelled as such (see the note below on its status).
- **Quota:** anonymous tier 400 API credits/day, global state-vector call
  is the 4-credit class (measured 2026-11-10); the cache respects this.
- **Attribution (as their terms require):** The OpenSky Network,
  https://opensky-network.org. Citation: Matthias Schäfer, Martin
  Strohmeier, Vincent Lenders, Ivan Martinovic and Matthias Wilhelm,
  "Bringing Up OpenSky: A Large-scale ADS-B Sensor Network for Research",
  Proceedings of the 13th IEEE/ACM International Symposium on
  Information Processing in Sensor Networks (IPSN), 2014.
- **Boundary, stated plainly:** anyone wanting this layer in a live or
  commercial product needs OpenSky's separate written licence. This
  repository is not that licence.

*Fixture note:* the 400-vector excerpt exists so the test suite can run
offline against the real response shape. It is a minimal, dated excerpt
of the provider's own public API response, never presented as live, and
the full-response counts are recorded separately in
`results/measurements.json`. If OpenSky objects, the excerpt can be
replaced with synthetic vectors shaped by the documented schema without
changing any parser behaviour.

## 2. Satellites — CelesTrak

- **Dataset/endpoint:** two-line element sets, GP data,
  `https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle`.
- **Terms:** https://celestrak.org/ (usage policy, checked 2026-11-10):
  CelesTrak data is free for use with attribution; CelesTrak asks that
  files be downloaded at most once per hour per dataset (the underlying
  supplemental source updates roughly every 8 hours) and that automated
  access use a valid User-Agent/email. Element sets are derived from the
  US Space Force 18th/19th Space Defense Squadron catalogue distributed
  via Space-Track; CelesTrak's posted terms state no redistribution
  restrictions for the public GP data beyond the usage policy above.
- **Our use:** fetch at most once per hour (3600 s in-memory cache),
  propagate positions locally with the SGP4 model (python-sgp4, MIT).
  Positions shown are *computed from published element sets* — the demo
  does not "track" anything, and the receipts panel says so.

## 3. Earthquakes — USGS

- **Dataset/endpoint:** `https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson` (magnitude 2.5+, past day).
- **Terms:** USGS-published information is in the public domain in the
  United States — https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits
  ("Most of the information presented on the USGS website is considered
  public domain information in the United States and may be distributed
  or copied"). Attribution to USGS is customary and given in the UI.
- **Our use:** fetch and display; feed is reviewed science, not a sensor
  stream — typical delays of minutes, and the panel shows the feed's own
  generation timestamp age on every fetch.

## 4. Wildfires — NASA FIRMS

- **Dataset/endpoint:** MODIS/VIIRS active-fire detections, FIRMS
  map-key API (CSV).
- **Terms:** NASA Earthdata guidance treats FIRMS data products as public
  domain / CC0; FIRMS asks users to acknowledge FIRMS and LANCE. API
  access needs a free personal MAP_KEY (operator signup at
  https://firms.modaps.eosdis.nasa.gov/api/map_key), 5,000
  transactions per 10 minutes.
- **Our use:** the key is an operator credential obtained by the repo
  owner's own signup, so **this demo ships the layer behind the optional
  `FIRMS_MAP_KEY` environment variable and renders a documented OFF
  state when no key is configured** — never a silent empty map. The
  parser and the off-state are covered by tests; no key ships with the
  repo.

## 5. Code dependencies (all permissive)

| Dependency | Licence |
|---|---|
| globe.gl (frontend globe renderer) | MIT |
| three (via globe.gl) | MIT |
| react, react-dom | MIT |
| vite, @vitejs/plugin-react | MIT |
| fastapi | MIT |
| sgp4 (python-sgp4) | MIT |
| httpx | BSD-3-Clause |
| uvicorn | BSD-3-Clause |
| pytest | MIT |

No copyleft or proprietary dependency is used; nothing in the stack
constrains this repository's own MIT licence.

Globe imagery: the frontend loads the earth-blue-marble / night-sky
example images distributed with the three-globe examples (NASA Blue
Marble imagery, public domain) from the jsDelivr CDN at runtime; no
imagery is vendored into this repository.
