"""Chatbot de bout en bout (API FastAPI + PostgreSQL de test, données d'échantillon et de démonstration)."""
import pytest
from fastapi.testclient import TestClient

from app import models as m
from app.main import app


@pytest.fixture
def client(seeded):
    with TestClient(app) as c:
        yield c


def ask(client, message, **kw):
    r = client.post("/api/chat", json={"message": message, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def _amlor5(client):
    items = client.get("/api/medicines/search", params={"q": "amlor 5 mg"}).json()["items"]
    return next(i["id"] for i in items if i["brand"] == "AMLOR" and i["dosage"] == "5 MG")


def test_darija_price_uses_database_and_flags_simulation(client):
    out = ask(client, "Ch7al taman dyal Doliprane 500mg ?")
    assert out["language"]["code"] == "darija_latin" and out["intent"]["resolved"] == "price"
    assert out["entities"]["dose"]["mg"] == 500.0
    assert {(x["brand"], x["dosage"]) for x in out["medicines"]} == {("DOLIPRANE", "500 MG")}
    assert out["contains_simulated_data"] is True and "FICTIF" in out["message"]
    assert any("SIMULÉES" in w for w in out["warnings"])


def test_darija_question_gets_a_darija_answer_when_templates_exist(client):
    out = ask(client, "Ch7al taman dyal AMLOR 5 mg ?")
    assert out["language"]["code"] == "darija_latin" and out["language"]["reply_language"] == "darija"
    assert "ma kaynch" in out["message"] and "AMLOR 5 MG" in out["message"] and "DH" not in out["message"]
    assert not any("rédigée en français" in w for w in out["warnings"])
    gen = ask(client, "Chnahuma les génériques dyal AMLOR 10 mg ?")
    assert gen["language"]["code"] == "darija_latin" and gen["intent"]["resolved"] == "generics"
    assert "AMEP 10 MG" in gen["message"] and "AMLOR 5" not in gen["message"]


def test_darija_falls_back_to_plain_french_rather_than_mixing(client):
    out = ask(client, "Ch7al taman dyal Doliprane 500mg ?")  # prix (fictif) : formulation darija non disponible
    assert out["language"]["reply_language"] == "fr" and "Prix publics" in out["message"]
    assert any("rédigée en français" in w for w in out["warnings"])


def test_on_duty_without_verified_data_never_points_to_141(client):
    for q in ("Quelles sont les pharmacies de garde à Casablanca aujourd'hui ?", "wach kayn pharmacie de garde f casa ?"):
        out = ask(client, q)
        assert out["intent"]["resolved"] == "on_duty" and "141" not in out["message"]
        if out["understanding"] == "information_unavailable":
            assert out["pharmacies"] == []


def test_exact_brand_wins_and_ties_are_reported_not_substituted(client):
    exact = ask(client, "Quelle est la substance active d'AMLOR 5 mg ?")
    assert [(x["brand"], x["dosage"]) for x in exact["medicines"]] == [("AMLOR", "5 MG")]
    amb = ask(client, "Prix d'amlo 5 mg")  # « amlo » : AMLOR et AMILO à égalité
    assert amb["understanding"] == "ambiguous" and "AMLOR" in amb["message"] and "AMILO" in amb["message"]
    assert amb["context_medicine"] is None


def test_explicit_dose_overrides_context_dose(client):
    first = ask(client, "Quelle est la substance active d'AMLOR 5 mg ?")
    conv = first["conversation_id"]
    ten = ask(client, "prix du 10 mg ?", conversation_id=conv)
    assert [(x["brand"], x["dosage"]) for x in ten["medicines"]] == [("AMLOR", "10 MG")]
    twenty = ask(client, "prix du 20 mg ?", conversation_id=conv)
    assert twenty["understanding"] == "dosage_not_found" and "DH" not in twenty["message"]


def test_conversation_contexts_are_isolated(client):
    a = ask(client, "Quels sont les génériques d'AMLOR 10 mg ?")
    b = ask(client, "Quelle est la substance active d'AMLOR 5 mg ?")
    assert a["context_medicine"]["dosage"] == "10 MG" and b["context_medicine"]["dosage"] == "5 MG"
    fa = ask(client, "et ses présentations ?", conversation_id=a["conversation_id"])
    fb = ask(client, "et ses présentations ?", conversation_id=b["conversation_id"])
    assert fa["medicines"][0]["id"] == a["context_medicine"]["id"] != fb["medicines"][0]["id"] == b["context_medicine"]["id"]
    # reprise par un possessif : jamais une suggestion approximative du catalogue à la place du contexte
    for q in ("et son prix ?", "et sa composition ?", "ch7al taman dyalo ?"):
        follow = ask(client, q, conversation_id=b["conversation_id"])
        assert [x["id"] for x in follow["medicines"]] == [b["context_medicine"]["id"]], q
    fresh = ask(client, "Quelle est sa substance active ?")  # nouvelle conversation : aucun contexte hérité
    assert fresh["context_medicine"] is None and fresh["understanding"] == "clarification_needed"
    # une question portant sur plusieurs dosages ne fixe pas un dosage arbitraire comme contexte
    assert ask(client, "Quels sont les dosages disponibles pour AMLOR ?")["context_medicine"] is None


def test_missing_dosage_is_never_substituted(client):
    out = ask(client, "prix doliprane 750 mg")
    assert out["understanding"] == "dosage_not_found"
    assert "500 MG" in out["message"] and "750" in out["message"]
    assert "DH" not in out["message"]  # aucun prix d'un autre dosage présenté comme réponse


def test_generics_of_amlor_come_from_ammps_register(client):
    out = ask(client, "Quels sont les génériques d'AMLOR 5 mg ?")
    assert out["intent"]["resolved"] == "generics" and out["understanding"] == "understood"
    assert "AMEP 5 MG" in out["message"] and "Répertoire AMMPS" in out["message"]
    assert any(s["code"].startswith("ammps") for s in out["sources"])


def test_context_from_pill_identifier_is_verified_and_used(client):
    med_id = _amlor5(client)
    out = ask(client, "شنو المادة الفعالة ديال هاد الدوا؟", context_medicine_id=med_id)
    assert out["language"]["reply_language"] == "ar" and out["intent"]["resolved"] == "active_ingredient"
    assert out["context_medicine"]["id"] == med_id and "AMLODIPINE" in out["message"]
    follow = ask(client, "et ses présentations ?", conversation_id=out["conversation_id"])
    assert follow["intent"]["resolved"] == "presentations" and follow["medicines"][0]["id"] == med_id


def test_unknown_context_id_is_ignored(client):
    out = ask(client, "prix ?", context_medicine_id=999999)
    assert any("Contexte ignoré" in w for w in out["warnings"]) and out["context_medicine"] is None
    assert out["understanding"] == "clarification_needed"


def test_absent_information_is_declared_absent(client):
    out = ask(client, "Quelles sont les contre-indications d'AMLOR 5 mg ?")
    assert out["understanding"] == "information_unavailable"
    assert "ne sont pas disponibles dans nos sources" in out["message"]


def test_unknown_medicine_is_not_found(client):
    out = ask(client, "prix du zorglubine")
    assert out["understanding"] == "not_found" and out["medicines"] == []


def test_medical_advice_and_emergency_are_refused(client):
    advice = ask(client, "j'ai mal à la tête, que prendre ?")
    assert advice["understanding"] == "refused_medical_advice" and "pharmacien" in advice["message"]
    urgent = ask(client, "mon fils a avalé tout le flacon")
    assert urgent["understanding"] == "emergency" and "141" in urgent["message"]


def test_posology_is_never_invented(client):
    out = ask(client, "combien de comprimés de doliprane 500 mg par jour ?")
    assert out["intent"]["resolved"] == "posology" and out["understanding"] == "information_unavailable"
    assert "médecin ou pharmacien" in out["message"]


def test_pharmacy_search_needs_a_city_and_flags_stock(client):
    ask_city = ask(client, "je cherche une pharmacie")
    assert ask_city["understanding"] == "clarification_needed"
    out = ask(client, "wach kayn doliprane 1000 mg f casa")
    assert out["entities"]["city"] == "Casablanca" and out["pharmacies"]
    assert "verified" not in {p["availability"]["kind"] for p in out["pharmacies"]}
    assert "pas vérifié" in out["message"]


def test_user_text_is_not_stored(client, seeded):
    out = ask(client, "Prix d'AMLOR 5 mg, je m'appelle Fatima et j'ai 45 ans")
    msgs = seeded.query(m.Message).filter(m.Message.conversation_id == out["conversation_id"]).all()
    user = [x for x in msgs if x.role == "user"]
    assert user and all("Fatima" not in x.content for x in user)
    assert client.delete(f"/api/chat/{out['conversation_id']}").json() == {"deleted": True}


def test_suggestions_for_medicine(client):
    med_id = _amlor5(client)
    data = client.get("/api/chat/suggestions", params={"medicine_id": med_id}).json()
    assert data["medicine"]["brand"] == "AMLOR" and any("génériques" in s for s in data["suggestions"])
    assert client.get("/api/chat/suggestions", params={"medicine_id": 999999}).status_code == 404


def test_message_validation(client):
    assert client.post("/api/chat", json={"message": ""}).status_code == 422
    assert client.post("/api/chat", json={"message": "x" * 1001}).status_code == 422
