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
- **Round-2 sub-layers (2026-11-10):** the same endpoint family serves
  `GROUP=stations` and `GROUP=starlink`. The receipt reports them as
  labelled sub-layers. On the round-2 measurement run the stations
  group, exactly as served, held 15 element sets (station modules and
  docked vehicles — the group is small because it is curated, and the
  receipt says "as served" rather than rounding it up), and the
  Starlink group held 10,619 sets — exactly the count obtained by
  counting STARLINK-prefixed names inside the active catalogue on the
  same run, two independent routes to the same number. Sub-layers
  overlap the active total; they are not additive.

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

## 6. Fireballs — NASA/JPL CNEOS (round 2, verified live 2026-11-10)

- **Dataset/endpoint:** `GET https://ssd-api.jpl.nasa.gov/fireball.api?limit=100`
  — fireball/bolide events reported by US Government sensors, with date,
  location, altitude, velocity and computed impact energy.
- **Terms:** NASA/JPL Small-Body Database APIs are public US Government
  services, published for open research use; no key, no registration.
  Attribution to NASA/JPL CNEOS is given in the UI.
- **Live check:** HTTP 200, 100 rows; 99 carried a location (1 row had
  no reported position and is counted, not plotted).
- **Verdict: IMPLEMENTED.** Receipt honesty: this is a reviewed event
  catalogue, not a stream — on the round-2 run the newest of the 100
  events was dated 2026-10-04, so the layer's feed-age receipt reads in
  weeks, and the UI says why.

## 7. Space weather — NOAA SWPC (round 2, verified live 2026-11-10)

- **Dataset/endpoints:** planetary K-index
  `https://services.swpc.noaa.gov/json/planetary_k_index_1m.json` and
  real-time solar wind `https://services.swpc.noaa.gov/json/rtsw/rtsw_wind_1m.json`.
- **Terms:** NOAA data is US public domain; SWPC publishes these JSON
  services for public use without a key.
- **Live check:** both HTTP 200; K-index rows current to the minute;
  solar-wind rows carry an active spacecraft source (SOLAR1 on the
  round-2 run) at ~528 km/s.
- **Verdict: IMPLEMENTED as a panel-only layer.** Space weather is a
  planetary index with no honest globe coordinates; the demo puts its
  numbers in the panel and draws no dots for it. (The older
  `products/solar-wind/plasma-*.json` paths returned 404 on the live
  check — the RTSW service is the live one, and that is what is wired.)

## 8. Tropical cyclones — NOAA NHC (round 2, verified live 2026-11-10)

- **Dataset/endpoint:** `https://www.nhc.noaa.gov/CurrentStorms.json` —
  active storms with classification, intensity, pressure, position and
  links to the official forecast-track and cone files (KMZ).
- **Terms:** NOAA/NHC products are US public domain, published for
  public use without a key.
- **Live check:** HTTP 200 with one active storm (Pena, Central
  Pacific) on the round-2 run.
- **Verdict: IMPLEMENTED.** Zero active storms is a normal state for
  much of the year and is reported as 0. Forecast cones are linked as
  the official KMZ in each storm's detail card, not redrawn — the
  geometry stays the forecaster's.

## 9. Earthquakes, second catalogue — EMSC SeismicPortal (CC BY 4.0)

- **Dataset/endpoint:** FDSN event service,
  `https://www.seismicportal.eu/fdsnws/event/1/query?format=json`
  (minmag 2.5, trailing 24 h), the EMSC-RTS catalogue aggregating
  dozens of national agencies.
- **Terms:** the SeismicPortal terms and the FDSN service page (both
  checked 2026-11-10) state that datasets and products from the data
  services are provided under the Creative Commons Attribution 4.0
  International licence (CC BY 4.0). Credit as prescribed:
  *EMSC-CSEM SeismicPortal, https://www.seismicportal.eu*.
- **Live check:** HTTP 200; 204 events in the same 24 h window where
  USGS listed 36.
- **Verdict: IMPLEMENTED, and it is the differentiator.** The receipts
  drawer reconciles the two catalogues event by event (origin time
  within 120 s and epicentre within 150 km, greedy closest-first):
  round-2 run — 32 events in both, 4 USGS-only, 172 EMSC-only, median
  magnitude disagreement on matched events 0.0. Coverage, not error,
  explains most of the gap; no other demo globe in this genre publishes
  its own inter-catalogue disagreement.

## 10. Vessels — Fintraffic Digitraffic AIS (CC BY 4.0)

- **Dataset/endpoint:** `https://meri.digitraffic.fi/api/ais/v1/locations`
  — live AIS vessel locations for Finnish waters.
- **Terms:** Fintraffic's open data is licensed CC BY 4.0 (Digitraffic
  terms of service, checked 2026-11-10). Required attribution, used
  verbatim in the UI and this repo: *Source: Fintraffic /
  digitraffic.fi, license CC 4.0 BY*.
- **Live check:** HTTP 200; 1,052 vessels, every one inside the
  Baltic box (lat 57.5–65.8, lng 16.5–35.8 on the round-2 run).
- **Verdict: IMPLEMENTED with the region labelled everywhere.** This
  is a regional feed and the demo says so in the layer name, the card
  and the claim readout. Global AIS feeds are commercial or key-gated
  (see section 13); the open globe's ships stop at this coastline, and
  that boundary is the honest picture.

## 11. US fire incidents — NIFC WFIGS (round 2, verified live 2026-11-10)

- **Dataset/endpoint:** WFIGS Incident Locations (Current), ArcGIS REST
  FeatureServer on services3.arcgis.com (org T4QMspbfLg3qTGWY), queried
  as GeoJSON — the public incident-point service behind NIFC's public
  maps, fed by the IRWIN interagency record.
- **Terms:** a US federal interagency public service published for
  public use without a key; NIFC publishes these layers as open data.
  Attribution to NIFC / WFIGS is given in the UI.
- **Live check:** HTTP 200; 464 current incident points, 912,342 total
  reported acres, largest single incident 283,283 acres.
- **Verdict: IMPLEMENTED as the incident-record counterpart to FIRMS.**
  Receipt honesty: 236 of the 464 "current incidents" on the round-2
  run are prescribed burns (names carrying RX) — a dispatch records
  system, not a sensor net. Incident points are wired; perimeter
  polygons (a separate WFIGS service, 62 current on the check) are
  not drawn in this round.

## 12. Ocean buoys — NOAA NDBC (round 2, verified live 2026-11-10)

- **Dataset/endpoint:** `https://www.ndbc.noaa.gov/data/latest_obs/latest_obs.txt`
  — latest observation per moored station, fixed-format text.
- **Terms:** NOAA data is US public domain; NDBC publishes the file for
  public use without a key.
- **Live check:** HTTP 200; 802 stations with a latest observation.
- **Verdict: IMPLEMENTED.** The parser is column-positioned text, not
  JSON — it is covered by a fixture test like every JSON parser here.

## 13. Considered and not wired (dated verdicts, 2026-11-10)

- **IODA (Georgia Tech) — REJECTED for this demo.** The signals API
  answers (per-country time series), but the outage-events API returns
  ASN- and country-level events with no coordinates and carries a
  payload copyright notice reserving rights to the Georgia Tech
  Research Corporation. There is no honest globe layer here without
  bolting on an external geolocation dataset and a separate licence
  review; neither was done, so IODA is recorded, not wired.
- **AISStream and OpenAQ — KEY-GATED, not wired.** Both need the
  operator's own API key/registration, the same class as FIRMS. They
  join the documented optional-key pattern: a future operator can add
  a key and a parser behind the same honest OFF state. No key was
  requested or created for this demo.
- **NOAA SWPC `products/solar-wind/*` JSON paths — DEAD.** Returned
  404 on the live check; replaced by the RTSW service in section 7.

## 14. Code dependencies (all permissive)

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
