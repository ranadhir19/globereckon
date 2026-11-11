import { useEffect, useMemo, useRef, useState } from "react";
import Globe from "globe.gl";

const LAYERS = [
  { id: "flights", name: "Flights", color: "#ffb454" },
  { id: "satellites", name: "Satellites", color: "#57d7ff" },
  { id: "earthquakes", name: "Earthquakes — USGS", color: "#ff5d5d" },
  { id: "quakes_emsc", name: "Earthquakes — EMSC", color: "#ff9d5d" },
  { id: "vessels", name: "Vessels — Baltic AIS", color: "#4de3b2" },
  { id: "buoys", name: "Ocean buoys", color: "#7db4ff" },
  { id: "storms", name: "Tropical cyclones", color: "#e879ff" },
  { id: "fireballs", name: "Fireballs", color: "#ffe14d" },
  { id: "wildfires_us", name: "US fire incidents", color: "#ff8a3d" },
  { id: "wildfires", name: "Wildfires — FIRMS", color: "#ff6b4d" },
  { id: "spaceweather", name: "Space weather", color: "#b49aff", panel: true },
];
const COLOR = Object.fromEntries(LAYERS.map((l) => [l.id, l.color]));
const GLOBE_LAYERS = LAYERS.filter((l) => !l.panel);

// Altitudes are exaggerated so low objects are visible at globe scale;
// the caption on the map says so. Flights ~11 km, satellites to GEO.
function altitudeOf(p) {
  if (p.__layer === "flights") return 0.012 + p.alt_km * 0.004;
  if (p.__layer === "satellites") return Math.min(0.45, 0.02 + p.alt_km * 0.00035);
  if (p.__layer === "fireballs") return 0.02 + Math.min(0.1, p.alt_km * 0.001);
  return 0.012;
}
function radiusOf(p) {
  if (p.__layer === "earthquakes" || p.__layer === "quakes_emsc")
    return 0.2 + (p.mag || 2.5) * 0.085;
  if (p.__layer === "storms") return 0.65;
  if (p.__layer === "wildfires_us")
    return 0.22 + Math.min(0.5, Math.log10((p.acres || 1) + 1) * 0.12);
  if (p.__layer === "satellites") return 0.14;
  return 0.18;
}
function fmt(n) {
  return n === null || n === undefined ? "—" : Number(n).toLocaleString("en-US");
}
function ageOf(r) {
  if (!r) return "—";
  if (r.staleness_s !== null && r.staleness_s !== undefined)
    return r.staleness_s >= 3600
      ? `${(r.staleness_s / 3600).toFixed(1)} h`
      : `${Math.round(r.staleness_s)} s`;
  if (r.median_epoch_age_h !== null && r.median_epoch_age_h !== undefined)
    return `${Number(r.median_epoch_age_h).toFixed(1)} h (element sets)`;
  return "—";
}
function detailRows(p) {
  const rows = [];
  const add = (k, v) => {
    if (v !== null && v !== undefined && v !== "") rows.push([k, String(v)]);
  };
  add("Layer", p.__layer);
  add("Position", `${p.lat.toFixed(3)}, ${p.lng.toFixed(3)}`);
  if (p.__layer === "flights") {
    add("Altitude", `${fmt(p.alt_km)} km`);
  }
  if (p.__layer === "satellites") {
    add("Altitude (computed)", `${fmt(p.alt_km)} km`);
    add("Note", "SGP4 propagation of a published element set");
  }
  if (p.__layer === "earthquakes" || p.__layer === "quakes_emsc") {
    add("Magnitude", p.mag);
    add("Depth", p.depth_km !== null && p.depth_km !== undefined ? `${p.depth_km} km` : null);
    add("Place", p.place);
    add("Origin time", p.time_epoch ? new Date(p.time_epoch * 1000).toISOString() : null);
    add("Catalogue ID", p.source_id);
    if (p.auth) add("Reporting agency", p.auth);
  }
  if (p.__layer === "vessels") {
    add("MMSI", p.mmsi);
    add("Speed over ground", p.sog_kn !== null && p.sog_kn !== undefined ? `${p.sog_kn} kn` : null);
    add("Course", p.cog !== null && p.cog !== undefined ? `${p.cog}°` : null);
    add("Heading", p.heading !== null && p.heading !== undefined && p.heading !== 511 ? `${p.heading}°` : null);
    add("Note", "Self-reported AIS; regional feed — Finnish/Baltic waters");
  }
  if (p.__layer === "buoys") {
    add("Station", p.station);
    add("Wind", p.wind_ms !== null && p.wind_ms !== undefined && p.wind_ms !== "MM" ? `${p.wind_ms} m/s at ${p.wind_dir}°` : null);
    add("Water temp", p.water_temp_c !== null && p.water_temp_c !== undefined && p.water_temp_c !== "MM" ? `${p.water_temp_c} °C` : null);
    add("Observed", p.time_epoch ? new Date(p.time_epoch * 1000).toISOString() : null);
  }
  if (p.__layer === "storms") {
    add("Classification", p.classification);
    add("Intensity", p.intensity_kt ? `${p.intensity_kt} kt` : null);
    add("Pressure", p.pressure_mb ? `${p.pressure_mb} mb` : null);
    add("Advisory updated", p.time_epoch ? new Date(p.time_epoch * 1000).toISOString() : null);
    add("Forecast cone (KMZ)", p.track_cone_kmz);
  }
  if (p.__layer === "fireballs") {
    add("Event (UTC)", p.date);
    add("Impact energy", p.impact_kt !== null && p.impact_kt !== undefined ? `${p.impact_kt} kt` : null);
    add("Altitude", p.alt_km ? `${p.alt_km} km` : null);
    add("Velocity", p.vel_kms ? `${p.vel_kms} km/s` : null);
    add("Note", "Catalogue event, published after review — not a live detection");
  }
  if (p.__layer === "wildfires_us") {
    add("Incident", p.name);
    add("State", p.state);
    add("Size", p.acres !== null && p.acres !== undefined ? `${fmt(p.acres)} acres` : null);
    add("Contained", p.contained_pct !== null && p.contained_pct !== undefined ? `${p.contained_pct}%` : null);
    add("Discovered", p.time_epoch ? new Date(p.time_epoch * 1000).toISOString() : null);
  }
  if (p.__layer === "wildfires") add("Detection", p.label);
  return rows;
}

export default function App() {
  const mountRef = useRef(null);
  const globeRef = useRef(null);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [enabled, setEnabled] = useState(
    Object.fromEntries(LAYERS.map((l) => [l.id, true]))
  );
  const [selected, setSelected] = useState(null);
  const [drawer, setDrawer] = useState(true);

  useEffect(() => {
    fetch("/api/layers")
      .then((r) => r.json())
      .then(setData)
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (!mountRef.current || globeRef.current) return;
    const g = Globe()(mountRef.current)
      .globeImageUrl("https://cdn.jsdelivr.net/npm/three-globe/example/img/earth-blue-marble.jpg")
      .backgroundImageUrl("https://cdn.jsdelivr.net/npm/three-globe/example/img/night-sky.png")
      .pointLat("lat")
      .pointLng("lng")
      .pointColor((p) => COLOR[p.__layer])
      .pointAltitude(altitudeOf)
      .pointRadius(radiusOf)
      .pointLabel((p) => `${p.__layer}: ${p.label || ""}`)
      .onPointClick((p) => setSelected(p));
    g.controls().autoRotate = true;
    g.controls().autoRotateSpeed = 0.35;
    globeRef.current = g;
  }, []);

  const points = useMemo(() => {
    if (!data) return [];
    return GLOBE_LAYERS.filter((l) => enabled[l.id])
      .flatMap((l) => (data.layers[l.id]?.points || []).map((p) => ({ ...p, __layer: l.id })));
  }, [data, enabled]);

  useEffect(() => {
    if (globeRef.current) globeRef.current.pointsData(points);
  }, [points]);

  const cross = data?.cross_source?.earthquakes_usgs_vs_emsc;

  return (
    <div className="layout">
      <aside className="panel left">
        <h1>globereckon</h1>
        <p className="tagline">
          A situational globe that shows its own receipts — every layer is
          measured on the fetch that drew it, and two earthquake catalogues
          are reconciled against each other in the open.
        </p>
        {data?.mode === "fixture" && (
          <div className="banner">
            FIXTURE MODE — recorded response excerpts, labelled, never live.
          </div>
        )}
        {error && <div className="banner err">API unreachable: {error}</div>}
        {!data && !error && <p className="muted">Fetching feeds…</p>}

        <button className="drawer-toggle" onClick={() => setDrawer(!drawer)}>
          {drawer ? "Hide receipts drawer" : "Show receipts drawer"}
        </button>

        {LAYERS.map((l) => {
          const r = data?.layers[l.id]?.receipt;
          return (
            <section key={l.id} className="card">
              <header>
                <label>
                  <input
                    type="checkbox"
                    checked={enabled[l.id]}
                    disabled={!!l.panel}
                    onChange={(e) => setEnabled({ ...enabled, [l.id]: e.target.checked })}
                  />{" "}
                  <span className="dot" style={{ background: l.color }} />
                  {l.name}
                </label>
                <span className={`chip ${r?.status || "…"}`}>{r?.status || "…"}</span>
              </header>
              {r && (
                <div className="receipt">
                  <div className="src">{r.source}</div>
                  <dl>
                    {r.panel_only ? (
                      <>
                        <div><dt>planetary K-index</dt><dd>{fmt(r.kp_latest)}</dd></div>
                        <div><dt>Kp max, 24 h</dt><dd>{fmt(r.kp_max_24h)}</dd></div>
                        <div><dt>solar wind</dt><dd>{r.wind_speed_kms ? `${r.wind_speed_kms} km/s` : "—"}</dd></div>
                        <div><dt>wind source craft</dt><dd>{r.wind_source || "—"}</dd></div>
                      </>
                    ) : (
                      <div><dt>objects live</dt><dd>{fmt(r.objects_live)}</dd></div>
                    )}
                    <div><dt>feed age at fetch</dt><dd>{ageOf(r)}</dd></div>
                    {r.median_position_age_s !== null && r.median_position_age_s !== undefined && (
                      <div><dt>median position age</dt><dd>{r.median_position_age_s}s</dd></div>
                    )}
                    {r.fetch && (
                      <div><dt>fetch</dt><dd>{r.fetch.latency_ms} ms · {(r.fetch.response_bytes / 1024).toFixed(0)} KB</dd></div>
                    )}
                    {r.max_impact_kt !== null && r.max_impact_kt !== undefined && (
                      <div><dt>largest impact</dt><dd>{r.max_impact_kt} kt</dd></div>
                    )}
                    {r.rx_count !== null && r.rx_count !== undefined && (
                      <div><dt>of which prescribed burns</dt><dd>{fmt(r.rx_count)}</dd></div>
                    )}
                  </dl>
                  {r.sublayers && (
                    <table className="boxes">
                      <tbody>
                        <tr><td>Active catalogue</td><td>{fmt(r.sublayers.active_total)}</td></tr>
                        <tr><td>Starlink (group total)</td><td>{fmt(r.sublayers.starlink_group_elements)}</td></tr>
                        <tr><td>Starlink counted in active, by name</td><td>{fmt(r.sublayers.starlink_in_active_by_name)}</td></tr>
                        <tr><td>Stations group, as served</td><td>{fmt(r.sublayers.stations_group_elements)}</td></tr>
                      </tbody>
                    </table>
                  )}
                  {r.coverage && (
                    <table className="boxes">
                      <tbody>
                        {Object.entries(r.coverage.probe_boxes).map(([k, v]) => (
                          <tr key={k}><td>{k}</td><td>{fmt(v)}</td></tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                  <p className="note">{r.coverage_note}</p>
                </div>
              )}
            </section>
          );
        })}

        <footer className="muted small">
          Non-commercial content demo. Flight data: OpenSky Network
          (non-commercial terms). Vessel data: Source: Fintraffic /
          digitraffic.fi, licence CC 4.0 BY. Earthquake comparison:
          EMSC-CSEM SeismicPortal (CC BY 4.0) vs USGS (public domain).
          Full record: DATA_SOURCES.md in the repo. Do not use for
          navigation or safety decisions.
        </footer>
      </aside>

      <div className="globe-wrap">
        <div ref={mountRef} className="globe" />
        <div className="globe-caption">
          Point altitudes are exaggerated for visibility. Satellite positions
          are computed (SGP4), not sensed. Click any point for its record.
        </div>
        {selected && (
          <div className="detail-card">
            <header>
              <span className="dot" style={{ background: COLOR[selected.__layer] }} />
              <strong>{selected.label || selected.__layer}</strong>
              <button className="close" onClick={() => setSelected(null)}>×</button>
            </header>
            <dl>
              {detailRows(selected).map(([k, v]) => (
                <div key={k}><dt>{k}</dt><dd>{v}</dd></div>
              ))}
            </dl>
          </div>
        )}
      </div>

      {drawer && (
        <aside className="panel right">
          <h2>Receipts</h2>
          <p className="tagline">
            Claimed vs measured, from this server's own fetches. The claims
            are the genre's marketing lines; the numbers are what the feeds
            actually returned.
          </p>

          {data?.claims?.length > 0 && (
            <section className="card">
              <header><strong>Claimed vs measured</strong></header>
              <table className="claims">
                <tbody>
                  {data.claims.map((c) => (
                    <tr key={c.claim}>
                      <td>“{c.claim}”</td>
                      <td className="num">{fmt(c.measured)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {data.claims.map((c) => (
                <p key={c.claim} className="note">{c.reading}</p>
              ))}
            </section>
          )}

          {cross && (
            <section className="card">
              <header><strong>Cross-source: USGS vs EMSC earthquakes</strong></header>
              <table className="claims">
                <tbody>
                  <tr><td>USGS events (24 h, M2.5+)</td><td className="num">{fmt(cross.usgs_total)}</td></tr>
                  <tr><td>EMSC events (24 h, M2.5+)</td><td className="num">{fmt(cross.emsc_total)}</td></tr>
                  <tr><td>In both catalogues</td><td className="num">{fmt(cross.matched)}</td></tr>
                  <tr><td>USGS only</td><td className="num">{fmt(cross.usgs_only)}</td></tr>
                  <tr><td>EMSC only</td><td className="num">{fmt(cross.emsc_only)}</td></tr>
                  <tr><td>Median magnitude disagreement on matches</td><td className="num">{cross.median_abs_mag_delta ?? "—"}</td></tr>
                </tbody>
              </table>
              <p className="note">
                Match rule: {cross.match_rule}. Two public catalogues of the
                same planet disagree mostly by coverage — EMSC hears far
                more small regional events through its national-agency
                network. Neither is “the” earthquake count; the overlap is
                the measurement.
              </p>
            </section>
          )}

          <section className="card">
            <header><strong>Every layer, this fetch</strong></header>
            <table className="claims">
              <tbody>
                {LAYERS.map((l) => {
                  const r = data?.layers[l.id]?.receipt;
                  if (!r) return null;
                  return (
                    <tr key={l.id}>
                      <td>{l.name}</td>
                      <td className="num">
                        {r.panel_only ? `Kp ${fmt(r.kp_latest)}` : fmt(r.objects_live)}
                      </td>
                      <td className="num">{ageOf(r)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="note">
              Columns: layer · objects returned on this fetch · age of the
              feed's own timestamp at fetch. A layer that fails reports its
              error in its card instead of drawing stale dots.
            </p>
          </section>
        </aside>
      )}
    </div>
  );
}
