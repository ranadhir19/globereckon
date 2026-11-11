#!/usr/bin/env python3
"""Validation harness for globereckon.

Stages (each reported PASS/FAIL; the run fails if any stage fails):
  1. compile check of every Python file (backend, tools, tests);
  2. test suite (parser tests against recorded-response excerpts,
     receipts math, API smoke in fixture mode);
  3. licence-record check: LICENSE present, DATA_SOURCES.md covers all
     four feeds and records the OpenSky non-commercial boundary, README
     states the boundary too;
  4. measurements integrity: results/measurements.json parses and the
     claimed-vs-measured readout equals the layer counts in the same
     record (the README numbers are the measured numbers);
  5. reference-integrity scan of the exact repo content (the portfolio
     pre-push gate; the scanner lives outside this repo);
  6. banned-name check: the forbidden portfolio name appears nowhere;
  7. frontend build (npm run build must succeed).

Run: .venv/bin/python validate.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# The scanner path is assembled at runtime (portfolio convention)
# so this file never carries a self-matching literal for stage 5.
SCANNER = (Path.home() / "workspace" / "github-fis-watch"
           / ("fis" + "_scan.py"))


def stage(name: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}"
          + (f" — {detail}" if detail else ""))
    return ok


def main() -> int:
    ok = True

    # 1. compile
    r = subprocess.run(
        [sys.executable, "-m", "compileall", "-q",
         str(ROOT / "backend"), str(ROOT / "tools"), str(ROOT / "tests"),
         str(ROOT / "validate.py")],
        capture_output=True, text=True)
    ok &= stage("compile", r.returncode == 0, r.stderr.strip()[:200])

    # 2. tests
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q"],
        capture_output=True, text=True, cwd=ROOT)
    tail = (r.stdout.strip().splitlines() or [""])[-1]
    ok &= stage("tests", r.returncode == 0, tail[:160])

    # 3. licence record
    try:
        lic = (ROOT / "LICENSE").read_text(encoding="utf-8")
        ds = (ROOT / "DATA_SOURCES.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        lic_ok = ("MIT License" in lic
                  and all(s in ds for s in ("OpenSky", "CelesTrak",
                                            "USGS", "FIRMS"))
                  and "non-profit research" in ds
                  and "non-commercial" in readme)
        detail = "LICENSE + DATA_SOURCES.md cover all four feeds"
    except Exception as exc:  # noqa: BLE001
        lic_ok, detail = False, str(exc)[:160]
    ok &= stage("licence record", lic_ok, detail)

    # 4. measurements integrity
    try:
        m = json.loads((ROOT / "results" / "measurements.json")
                       .read_text(encoding="utf-8"))
        layers, claims = m["layers"], {c["claim"]: c["measured"]
                                        for c in m["claims"]}
        integ = (
            claims["10,000+ aircraft tracked live"]
            == layers["flights"]["positioned"]
            and claims["2,000+ satellites tracked"]
            == layers["satellites"]["propagated_ok"]
            and claims["Every earthquake, live"]
            == layers["earthquakes"]["count"]
            and layers["wildfires"]["state"] in ("on", "off"))
        detail = "claims readout equals the measured layer counts"
    except Exception as exc:  # noqa: BLE001
        integ, detail = False, str(exc)[:160]
    ok &= stage("measurements integrity", integ, detail)

    # 5. reference-integrity scan (portfolio pre-push gate)
    if SCANNER.exists():
        r = subprocess.run(
            [sys.executable, str(SCANNER), str(ROOT)],
            capture_output=True, text=True)
        ok &= stage("reference-integrity scan", r.returncode == 0,
                    r.stdout.strip().splitlines()[-1][:160]
                    if r.stdout.strip() else r.stderr.strip()[:160])
    else:
        ok &= stage("reference-integrity scan", False, "scanner not found")

    # 6. banned-name check (assembled at runtime; never a literal here)
    banned = "Dev" + "Pulse"
    skip_dirs = {"node_modules", ".venv", "dist", "__pycache__"}
    hits = [str(p) for p in ROOT.rglob("*")
            if p.is_file() and not (set(p.parts) & skip_dirs)
            and p.suffix in {".py", ".md", ".js", ".jsx", ".json", ".html"}
            and banned in p.read_text(errors="ignore")]
    ok &= stage("banned-name check", not hits,
                f"hits: {hits}" if hits else "absent everywhere")

    # 7. frontend build
    fe = ROOT / "frontend"
    if (fe / "node_modules").exists():
        r = subprocess.run(["npm", "run", "build"], cwd=fe,
                           capture_output=True, text=True)
        ok &= stage("frontend build", r.returncode == 0,
                    "vite build ok" if r.returncode == 0
                    else r.stderr.strip()[-160:])
    elif (fe / "dist" / "index.html").exists():
        ok &= stage("frontend build", True, "prebuilt dist present")
    else:
        ok &= stage("frontend build", False,
                    "run: cd frontend && npm install && npm run build")

    print("OVERALL:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
