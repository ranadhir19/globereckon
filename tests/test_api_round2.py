"""Round-2 API smoke in fixture mode: new layers, panel layer, cross-source."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

EXPECTED_LAYERS = {
    "flights", "satellites", "earthquakes", "quakes_emsc", "wildfires",
    "wildfires_us", "vessels", "storms", "fireballs", "buoys",
    "spaceweather",
}


def test_all_round2_layers_present_with_receipts():
    body = client.get("/api/layers").json()
    assert set(body["layers"]) == EXPECTED_LAYERS
    for name, layer in body["layers"].items():
        assert layer["receipt"]["mode"] == "fixture", name
        assert "coverage_note" in layer["receipt"], name
        assert "cadence_note" in layer["receipt"], name


def test_new_globe_layers_have_points():
    body = client.get("/api/layers").json()
    for name in ("quakes_emsc", "vessels", "fireballs", "buoys",
                 "wildfires_us"):
        assert body["layers"][name]["receipt"]["objects_live"] > 0, name
        assert len(body["layers"][name]["points"]) > 0, name


def test_spaceweather_is_panel_only_and_honest_about_it():
    body = client.get("/api/layers").json()
    sw = body["layers"]["spaceweather"]
    assert sw["points"] == []
    assert sw["receipt"]["panel_only"] is True
    assert sw["receipt"]["objects_live"] is None
    assert sw["receipt"]["kp_latest"] is not None


def test_satellite_sublayers_reported():
    body = client.get("/api/layers").json()
    sub = body["layers"]["satellites"]["receipt"]["sublayers"]
    assert sub["active_total"] > 0
    assert sub["stations_group_elements"] == 15
    assert sub["stations_group_propagated"] == 15


def test_cross_source_block_is_internally_consistent():
    body = client.get("/api/layers").json()
    x = body["cross_source"]["earthquakes_usgs_vs_emsc"]
    usgs_n = body["layers"]["earthquakes"]["receipt"]["objects_live"]
    emsc_n = body["layers"]["quakes_emsc"]["receipt"]["objects_live"]
    assert x["usgs_total"] == usgs_n
    assert x["emsc_total"] == emsc_n
    assert x["matched"] + x["usgs_only"] == usgs_n
    assert x["matched"] + x["emsc_only"] == emsc_n


def test_receipts_endpoint_carries_cross_source_and_five_claims():
    body = client.get("/api/receipts").json()
    assert "earthquakes_usgs_vs_emsc" in body["cross_source"]
    claims = {c["claim"] for c in body["claims"]}
    assert "Every ship, tracked worldwide" in claims
    assert "All US wildfires, live" in claims
