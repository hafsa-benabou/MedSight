import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import get_db
from app.main import app


@pytest.fixture
def client(seeded):
    with TestClient(app) as c:
        yield c


def _id(client, q):
    return client.get("/api/medicines/search", params={"q": q}).json()["items"][0]["id"]


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["database"] == "ok"


def test_typo_is_corrected_and_dosage_kept(client):
    data = client.get("/api/medicines/search", params={"q": "dolipran 500mg"}).json()
    assert data["meta"]["dosage_found"] is True and data["meta"]["did_you_mean"] == "DOLIPRANE"
    assert {(i["brand"], i["dosage"]) for i in data["items"]} == {("DOLIPRANE", "500 MG")}


def test_missing_dosage_is_never_substituted(client):
    data = client.get("/api/medicines/search", params={"q": "doliprane 750 mg"}).json()
    assert data["items"] == [] and data["meta"]["dosage_found"] is False
    assert {"500 MG", "1000 MG"} <= set(data["meta"]["available_dosages"])


def test_accent_and_case_insensitive_ingredient_search(client):
    brands = {i["brand"] for i in client.get("/api/medicines/search", params={"q": "PARACÉTAMOL"}).json()["items"]}
    assert {"DOLIPRANE", "EFFERALGAN", "PARADEMO"} <= brands


def test_detail_exposes_provenance(client):
    d = client.get(f"/api/medicines/{_id(client, 'a.v.t')}").json()
    pres = {p["label"]: p for p in d["presentations"]}
    assert pres["BOITE DE 10"]["ppv"] == 10.7 and pres["BOITE DE 10"]["ean13"] == "6118000031055"
    assert pres["BOITE DE 10"]["source"]["code"] == "ammps_medicaments" and pres["BOITE DE 10"]["price_as_of"] == "2026-10-01"
    assert d["clinical_sections"] == []


def test_generics_split_regulatory_and_composition(client):
    g = client.get(f"/api/medicines/{_id(client, 'amlor 5 mg')}/generics").json()
    assert g["regulatory"][0]["group"] == "AMLODIPINE 5 MG COMPRIME"
    assert any(x["label"].startswith("AMEP 5 MG") for x in g["regulatory"][0]["members"])
    d = client.get(f"/api/medicines/{_id(client, 'doliprane 500mg')}/generics").json()
    assert d["regulatory"] == [] and any(c["brand"] == "PARADEMO" and c["same_form"] for c in d["pharmacological"])


def test_pharmacy_stock_is_never_presented_as_verified(client):
    med = _id(client, "doliprane 1000 mg")
    data = client.get("/api/pharmacies/search", params={"city": "casa", "medicine_id": med}).json()
    kinds = {i["availability"]["kind"] for i in data["items"]}
    assert data["city"] == "Casablanca" and kinds <= {"simulated", "unverified"} and "verified" not in kinds
    assert data["stock_notice"].startswith("Stock non vérifié")


def test_database_unavailable_returns_503(seeded):
    def broken():
        raise OperationalError("SELECT 1", {}, Exception("connexion refusée"))
        yield
    app.dependency_overrides[get_db] = broken
    try:
        with TestClient(app) as c:
            r = c.get("/api/medicines/search", params={"q": "x"})
        assert r.status_code == 503 and r.json()["error"]["code"] == "database_unavailable"
    finally:
        app.dependency_overrides.clear()
