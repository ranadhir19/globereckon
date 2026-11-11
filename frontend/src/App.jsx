import { useEffect, useMemo, useRef, useState } from "react";
import Globe from "globe.gl";

const LAYERS = [
  { id: "flights", name: "Flights", color: "#ffb454" },
  { id: "satellites", name: "Satellites", color: "#57d7ff" },
  { id: "earthquakes", name: "Earthquakes", color: "#ff5d5d" },
  { id: "wildfires", name: "Wildfires", color: "#ff8a3d" },
];
const COLOR = Object.fromEntries(LAYERS.map((l) => [l.id, l.color]));

// Altitudes are exaggerated so low objects are visible at globe scale;
// the panel says so. Flights ~11 km, satellites 400-40,000 km.
function altitudeOf(p) {
  if (p.__layer === "flights") return 0.012 + p.alt_km * 0.004;
  if (p.__layer === "satellites") return Math.min(0.45, 0.02 + p.alt_km * 0.00035);
  return 0.012;
}
function radiusOf(p) {
  if (p.__layer === "earthquakes") return 0.22 + (p.mag || 2.5) * 0.09;
  if (p.__layer === "satellites") return 0.14;
  return 0.18;
}
function fmt(n) {
  return n === null || n === undefined ? "—" : n.toLocaleString("en-US");
}

export default function App() {
  const mountRef = useRef(null);
  const globeRef = useRef(null);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [enabled, setEnabled] = useState({
    flights: true, satellites: true, earthquakes: true, wildfires: true,
  });

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
      .pointLabel((p) => `${p.__layer}: ${p.label || ""}`);
    g.controls().autoRotate = true;
    g.controls().autoRotateSpeed = 0.35;
    globeRef.current = g;
  }, []);

  const points = useMemo(() => {
    if (!data) return [];
    return LAYERS.filter((l) => enabled[l.id])
      .flatMap((l) => (data.layers[l.id]?.points || []).map((p) => ({ ...p, __layer: l.id })));
  }, [data, enabled]);

  useEffect(() => {
    if (globeRef.current) globeRef.current.pointsData(points);
  }, [points]);

  return (
    <div className="layout">
      <div className="globe-wrap">
        <div ref={mountRef} className="globe" />
        <div className="globe-caption">
          Point altitudes are exaggerated for visibility. Satellite positions
          are computed (SGP4), not sensed.
        </div>
      </div>
      <aside className="panel">
        <h1>globereckon</h1>
        <p className="tagline">
          A situational globe that shows its own receipts: every layer below
          is measured on the fetch that drew it.
        </p>
        {data?.mode === "fixture" && (
          <div className="banner">
            FIXTURE MODE — recorded response excerpts, labelled, never live.
          </div>
        )}
        {error && <div className="banner err">API unreachable: {error}</div>}
        {!data && !error && <p className="muted">Fetching feeds…</p>}

        {LAYERS.map((l) => {
          const layer = data?.layers[l.id];
          const r = layer?.receipt;
          return (
            <section key={l.id} className="card">
              <header>
                <label>
                  <input
                    type="checkbox"
                    checked={enabled[l.id]}
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
                    <div><dt>objects live</dt><dd>{fmt(r.objects_live)}</dd></div>
                    {r.staleness_s !== null && r.staleness_s !== undefined && (
                      <div><dt>feed age at fetch</dt><dd>{r.staleness_s}s</dd></div>
                    )}
                    {r.median_epoch_age_h !== null && r.median_epoch_age_h !== undefined && (
                      <div><dt>median element age</dt><dd>{Number(r.median_epoch_age_h).toFixed(1)}h</dd></div>
                    )}
                    {r.median_position_age_s !== null && r.median_position_age_s !== undefined && (
                      <div><dt>median position age</dt><dd>{r.median_position_age_s}s</dd></div>
                    )}
                    {r.fetch && (
                      <div><dt>fetch</dt><dd>{r.fetch.latency_ms} ms · {(r.fetch.response_bytes / 1024).toFixed(0)} KB</dd></div>
                    )}
                  </dl>
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
                  <p className="note muted">{r.cadence_note}</p>
                </div>
              )}
            </section>
          );
        })}

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

        <footer className="muted small">
          Non-commercial content demo. Flight data: OpenSky Network
          (non-commercial terms — see DATA_SOURCES.md in the repo). Do not
          use for navigation or safety decisions.
        </footer>
      </aside>
    </div>
  );
}
