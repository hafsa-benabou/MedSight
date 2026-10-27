"""Pipeline NLP du chatbot sans base de données : langue, intention, entités (vocabulaire fourni)."""
import pytest

from app.nlp.entities import Vocabulary, extract_entities
from app.nlp.intents import detect_intent
from app.nlp.language import detect_language
from app.nlp.text import normalize_text, skeleton_latin

BRANDS = ["doliprane", "amlor", "amep", "efferalgan", "abilify"]
VOCAB = Vocabulary({b: b for b in BRANDS}, {skeleton_latin(b): b for b in BRANDS},
                   {"paracetamol": (1, "PARACETAMOL"), "amlodipine": (2, "AMLODIPINE")})


@pytest.mark.parametrize("message,lang", [
    ("Ch7al taman dyal Doliprane 500mg ?", "darija_latin"),
    ("Je cherche une pharmacie à Rabat.", "fr"),
    ("شنو المادة الفعالة ديال هاد الدوا؟", "darija"),
    ("ما هو ثمن هذا الدواء", "ar"),
    ("What is the price of Abilify", "en"),
])
def test_language(message, lang):
    assert detect_language(message).code == lang


@pytest.mark.parametrize("message,intent", [
    ("Ch7al taman dyal Doliprane 500mg ?", "price"),
    ("Je cherche une pharmacie à Rabat.", "pharmacy_search"),
    ("شنو المادة الفعالة ديال هاد الدوا؟", "active_ingredient"),
    ("Quels sont les génériques d'AMLOR 5 mg ?", "generics"),
    ("generiqes du paracetamol", "generics"),  # faute d'orthographe
    ("quels dosages pour amlor", "dosages"),
    ("contre-indications amlor", "precautions"),
    ("pharmacie de garde casa", "on_duty"),
    ("wach kayn doliprane f casa", "availability"),
])
def test_intent(message, intent):
    assert detect_intent(message).name == intent


@pytest.mark.parametrize("message,intent", [
    ("j'ai avalé tout le flacon de doliprane, quel prix ?", "emergency"),
    ("combien de comprimés de doliprane par jour, et le prix ?", "posology"),
    ("j'ai mal à la tête que prendre ?", "medical_advice"),
    ("chhal mn wa7da nakhod mn doliprane", "posology"),
])
def test_safety_intents_take_priority(message, intent):
    assert detect_intent(message).name == intent


def test_entities_brand_typo_dose_and_city():
    e = extract_entities("dolipran 750 mg f casa", VOCAB)
    assert [m.brand for m in e.medicines] == ["doliprane"] and e.medicines[0].method == "fuzzy"
    assert (e.dose.value, e.dose.unit, e.dose.mg) == (750.0, "mg", 750.0)  # jamais « corrigé » en 500
    assert e.city == "Casablanca"


def test_entities_arabic_script_brand_and_bare_number():
    e = extract_entities("شحال ثمن دوليبران 500", VOCAB)
    assert [m.brand for m in e.medicines] == ["doliprane"] and e.medicines[0].method == "arabic_skeleton"
    assert (e.dose.value, e.dose.unit) == (500.0, None)


def test_entities_ingredient_not_taken_for_brand():
    e = extract_entities("prix du paracétamol", VOCAB)
    assert e.medicines == [] and [i.name for i in e.ingredients] == ["PARACETAMOL"]


def test_no_false_brand_on_common_words():
    e = extract_entities("je cherche une pharmacie à Rabat", VOCAB)
    assert e.medicines == [] and e.city == "Rabat"
    assert normalize_text("Rabat") == "rabat"
