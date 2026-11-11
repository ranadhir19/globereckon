"""API smoke in fixture mode: layers assembled, receipts honest, FIRMS off."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["mode"] == "fixture"


def test_layers_carry_receipts_and_fixture_labels():
    r = client.get("/api/layers")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "fixture"
    flights = body["layers"]["flights"]
    assert flights["receipt"]["mode"] == "fixture"
    assert flights["receipt"]["objects_live"] > 0
    assert "coverage" in flights["receipt"]
    sats = body["layers"]["satellites"]
    assert sats["receipt"]["objects_live"] >= 28
    assert sats["receipt"]["median_epoch_age_h"] is not None
    # FIRMS: no key in the test env -> documented OFF state, never a fake zero
    fires = body["layers"]["wildfires"]
    assert fires["receipt"]["status"] == "off"
    assert fires["receipt"]["objects_live"] is None
    assert fires["points"] == []


def test_claims_use_fixture_counts_not_marketing_numbers():
    body = client.get("/api/layers").json()
    measured = {c["claim"]: c["measured"] for c in body["claims"]}
    assert measured["10,000+ aircraft tracked live"] == \
        body["layers"]["flights"]["receipt"]["objects_live"]
