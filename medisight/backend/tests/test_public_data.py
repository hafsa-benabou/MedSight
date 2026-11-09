"""API publique (SHOW_SIMULATED_DATA=false) : aucune donnée de démonstration simulée n'est exposée, les données réelles restent accessibles."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import models as m
from app.core.config import get_settings
from app.main import app


@pytest.fixture
def public(seeded, monkeypatch):
    monkeypatch.setattr(get_settings(), "show_simulated_data", False)
    with TestClient(app) as c:
        yield c


def _sim_ids(db, model):
    return set(db.scalars(select(model.id).where(model.data_status == "simulated")))


def test_catalog_excludes_simulated(public, seeded):
    assert _sim_ids(seeded, m.Medicine), "le jeu de test doit contenir des médicaments simulés"
    for q in ("", "doliprane", "paracetamol", "efferalgan"):
        items = public.get("/api/medicines/search", params={"q": q, "size": 100}).json()["items"]
        assert all(i["data_status"] != "simulated" for i in items)
        assert all(p["data_status"] != "simulated" for i in items for p in i["presentations"])
    assert public.get("/api/medicines/search", params={"q": "doliprane"}).json()["total"] == 0
    assert public.get("/api/medicines/search", params={"q": "simulated", "status": "simulated"}).json()["total"] == 0
    sim_id = min(_sim_ids(seeded, m.Medicine))
    assert public.get(f"/api/medicines/{sim_id}").status_code == 404
    assert public.get(f"/api/medicines/{sim_id}/generics").status_code == 404
    assert not any(c["data_status"] == "simulated" for c in public.get("/api/medicines/autocomplete", params={"q": "do"}).json())


def test_real_medicines_still_available(public):
    items = public.get("/api/medicines/search", params={"q": "amlor 5 mg"}).json()["items"]
    amlor = next(i for i in items if i["brand"] == "AMLOR" and i["dosage"] == "5 MG")
    assert amlor["data_status"] == "official" and amlor["source"]["code"] == "ammps_generiques"
    assert public.get(f"/api/medicines/{amlor['id']}").status_code == 200
    gen = public.get(f"/api/medicines/{amlor['id']}/generics").json()
    assert gen["regulatory"] and all(c["data_status"] != "simulated" for c in gen["pharmacological"])


def test_pharmacies_and_duty_exclude_simulated(public):
    for city in ("Casablanca", "Rabat", None):
        params = {"city": city} if city else {}
        data = public.get("/api/pharmacies", params=params).json()
        assert all(p["data_status"] != "simulated" and "fictive" not in p["name"].lower() for p in data["items"])
        assert all(p.get("availability", {}).get("kind") != "simulated" for p in data["items"])
        assert all(s["data_status"] != "simulated" for s in public.get("/api/pharmacies/on-duty", params=params).json()["items"])
    rabat = public.get("/api/pharmacies", params={"city": "Rabat"}).json()["items"]
    assert rabat and all(p["source"]["code"] == "ammps_pharmacies" for p in rabat)


def test_chat_never_uses_simulated_data(public, seeded):
    for q in ("Ch7al taman dyal Doliprane 500mg ?", "Quels sont les génériques de Doliprane 1000 mg ?",
              "Je cherche une pharmacie à Casablanca", "pharmacie de garde à Rabat", "wach kayn doliprane f casa"):
        out = public.post("/api/chat", json={"message": q}).json()
        assert out["contains_simulated_data"] is False, q
        assert all(x["data_status"] != "simulated" for x in out["medicines"]), q
        assert all(p["data_status"] != "simulated" for p in out["pharmacies"]), q
        assert all(s["data_status"] != "simulated" for s in out["sources"]), q
        assert "FICTIF" not in out["message"] and "SIMULATION" not in out["message"] and "fictive" not in out["message"], q
    out = public.post("/api/chat", json={"message": "Ch7al taman dyal Doliprane 500mg ?"}).json()
    assert out["understanding"] == "not_found" and out["medicines"] == []
    sim_id = min(_sim_ids(seeded, m.Medicine))
    assert public.get("/api/chat/suggestions", params={"medicine_id": sim_id}).status_code == 404
    ctx = public.post("/api/chat", json={"message": "Quel est son prix ?", "context_medicine_id": sim_id}).json()
    assert ctx["context_medicine"] is None and any("Contexte ignoré" in w for w in ctx["warnings"])
    for s in public.get("/api/chat/suggestions").json()["suggestions"]:
        assert "doliprane" not in s.lower()


def test_chat_real_answers_unchanged(public):
    out = public.post("/api/chat", json={"message": "Quelle est la substance active d'AMLOR ?"}).json()
    assert out["intent"]["resolved"] == "active_ingredient" and "AMLODIPINE" in out["message"]
    out = public.post("/api/chat", json={"message": "Ch7al taman dyal Abilify 10 mg ?"}).json()
    assert out["language"]["code"] == "darija_latin" and "1 200,00" in out["message"].replace(" ", " ").replace("\xa0", " ")


def test_sources_hide_demo_but_health_counts_all(public):
    codes = {s["code"] for s in public.get("/api/sources").json()}
    assert "demo_simulated" not in codes and "ammps_medicaments" in codes
    h = public.get("/api/health").json()
    assert h["simulated_data_exposed"] is False and h["medicines_by_status"].get("simulated", 0) > 0
