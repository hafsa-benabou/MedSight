"""Extraction d'entités d'un message : médicament (nom commercial), substance active, dosage, ville.

Les noms sont rapprochés du vocabulaire de la base PostgreSQL (jamais d'une liste figée) : tolérance aux fautes
(« dolipran »), écriture arabe (« دوليبران » via le squelette consonantique) et arabizi. Un dosage lu n'est jamais
corrigé : « 750 mg » reste 750 mg, même si seul 500 mg existe."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from decimal import Decimal

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.nlp.cities import CITY_LOOKUP
from app.nlp.intents import TRIGGER_TOKENS
from app.nlp.text import arabic_variants, has_arabic, normalize_text, skeleton_arabic, skeleton_latin

_UNIT_MAP = {"mg": "mg", "mgr": "mg", "ملغ": "mg", "مغ": "mg", "ملغرام": "mg", "g": "g", "gr": "g", "غ": "g", "غرام": "g",
             "mcg": "µg", "µg": "µg", "μg": "µg", "ug": "µg", "ml": "ml", "مل": "ml", "ui": "ui", "%": "%"}
_MASS_MG = {"mg": Decimal(1), "g": Decimal(1000), "µg": Decimal("0.001")}
_DOSE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?) ?(mgr|mg|g|gr|mcg|µg|μg|ug|ml|ui|%|ملغرام|ملغ|مغ|غرام|غ|مل)(?![^\W\d_])")
_BARE_NUMBER = re.compile(r"^\d{1,4}(?:\.\d+)?$")
# Mots courants à ne jamais prendre pour un nom de médicament (mots outils, interrogatifs, darija)
STOPWORDS = {
    "le", "la", "les", "de", "du", "des", "un", "une", "et", "ou", "en", "a", "au", "aux", "est", "sont", "je", "tu",
    "il", "elle", "on", "nous", "vous", "me", "moi", "ce", "cet", "cette", "ces", "mon", "ma", "mes", "quel", "quelle",
    "quels", "quelles", "qui", "que", "quoi", "pour", "par", "sur", "dans", "avec", "sans", "pas", "plus", "y", "d", "l",
    "s", "qu", "c", "j", "n", "m", "t", "medicament", "medicaments", "dwa", "dawa", "doua", "ville", "svp", "stp", "merci",
    "bonjour", "salam", "dyal", "dial", "had", "hada", "hadi", "wach", "fin", "chno", "ach", "bghit", "3afak", "f", "fi",
    "b", "l", "m3a", "mo3a", "the", "of", "is", "what", "for", "and", "existe", "cherche", "chercher", "trouver",
    "donne", "donner", "connaitre", "savoir", "info", "infos", "information", "informations", "fiche", "rien", "tout",
    "شنو", "اش", "واش", "ديال", "هاد", "هادا", "هادي", "فين", "في", "من", "على", "الى", "عن", "هل", "ما", "ماهو", "ماهي",
    "دوا", "الدوا", "الدواء", "دواء", "بغيت", "عافاك", "مدينه", "ف", "ب", "ل", "و", "شي", "كاين", "هو", "هي", "لي",
}


@dataclass
class MedicineMention:
    text: str  # segment du message
    brand: str  # nom commercial reconnu (forme normalisée de la base)
    score: float  # similarité 0-100
    method: str  # exact | fuzzy | arabic_skeleton | alias


@dataclass
class IngredientMention:
    text: str
    ingredient_id: int
    name: str
    score: float


@dataclass
class DoseMention:
    text: str
    value: float
    unit: str | None  # None : nombre nu (« doliprane 500 ») ; comparé à la valeur imprimée du dosage
    mg: float | None


@dataclass
class Entities:
    medicines: list[MedicineMention] = field(default_factory=list)
    ingredients: list[IngredientMention] = field(default_factory=list)
    dose: DoseMention | None = None
    city: str | None = None
    city_text: str | None = None

    def summary(self) -> dict:
        return asdict(self)


@dataclass
class Vocabulary:
    brands: dict[str, str]  # forme normalisée -> forme normalisée de la marque (alias compris)
    brand_skeletons: dict[str, str]  # squelette consonantique -> marque normalisée
    ingredients: dict[str, tuple[int, str]]  # terme normalisé -> (id, nom)


def load_vocabulary(db: Session) -> Vocabulary:
    brands: dict[str, str] = {}
    for b in db.scalars(select(m.Medicine.brand_normalized).distinct()):
        if b:
            brands[b] = b
    for alias, brand in db.execute(select(m.MedicineAlias.alias_normalized, m.Medicine.brand_normalized)
                                   .join(m.Medicine, m.Medicine.id == m.MedicineAlias.medicine_id)):
        brands.setdefault(alias, brand)
    skeletons: dict[str, str] = {}
    for b in brands.values():
        sk = skeleton_latin(b)
        if len(sk) >= 3:
            skeletons.setdefault(sk, b)
    ingredients: dict[str, tuple[int, str]] = {}
    for ing in db.scalars(select(m.ActiveIngredient)):
        for term in [ing.name, ing.inn_en, ing.name_ar, *(ing.synonyms or []), *(ing.search_terms or [])]:
            t = normalize_text(term)
            if t:
                ingredients.setdefault(t, (ing.id, ing.name))
    return Vocabulary(brands, skeletons, ingredients)


def _ngrams(tokens: list[str], max_n: int = 3):
    for n in range(max_n, 0, -1):
        for i in range(len(tokens) - n + 1):
            yield i, n, " ".join(tokens[i:i + n])


def _candidate(tok: str) -> bool:
    return tok not in STOPWORDS and not _BARE_NUMBER.match(tok) and tok not in _UNIT_MAP and len(tok) >= 3


def extract_dose(norm: str, after_brand_tokens: list[str] | None = None) -> DoseMention | None:
    hit = _DOSE.search(norm)
    if hit:
        value, unit = Decimal(hit.group(1)), _UNIT_MAP[hit.group(2)]
        mg = float(value * _MASS_MG[unit]) if unit in _MASS_MG else None
        return DoseMention(hit.group(0), float(value), unit, mg)
    for tok in after_brand_tokens or []:  # « doliprane 500 » : nombre nu juste après le nom
        if _BARE_NUMBER.match(tok):
            return DoseMention(tok, float(tok), None, None)
    return None


def extract_city(tokens: list[str]) -> tuple[str | None, str | None]:
    for _, _, gram in _ngrams(tokens):
        variants = arabic_variants(gram) if has_arabic(gram) else [gram]
        for v in variants:
            if v in CITY_LOOKUP:
                return CITY_LOOKUP[v], gram
    return None, None


def extract_entities(message: str, vocab: Vocabulary) -> Entities:
    norm = normalize_text(message)
    tokens = norm.split()
    ent = Entities()
    ent.city, ent.city_text = extract_city(tokens)
    city_tokens = set((ent.city_text or "").split())
    used: set[int] = set()

    def take(i: int, n: int) -> None:
        used.update(range(i, i + n))

    # 1. substances actives (avant les marques : « paracetamol » ne doit pas devenir une marque proche)
    for i, n, gram in _ngrams(tokens):
        if used & set(range(i, i + n)) or not all(_candidate(t) or n > 1 for t in gram.split()):
            continue
        variants = arabic_variants(gram) if has_arabic(gram) else [gram]
        hit = next((v for v in variants if v in vocab.ingredients), None)
        score = 100.0
        if hit is None and len(gram) >= 6 and not has_arabic(gram):
            best = max(vocab.ingredients, key=lambda t: fuzz.ratio(gram, t), default=None)
            if best and fuzz.ratio(gram, best) >= 88:
                hit, score = best, fuzz.ratio(gram, best)
        if hit:
            ing_id, name = vocab.ingredients[hit]
            ent.ingredients.append(IngredientMention(gram, ing_id, name, round(score, 1)))
            take(i, n)

    # 2. noms commerciaux
    for i, n, gram in _ngrams(tokens):
        parts = gram.split()
        if used & set(range(i, i + n)) or not _candidate(parts[0]) or not _candidate(parts[-1]):
            continue
        if set(parts) & city_tokens or all(p in TRIGGER_TOKENS for p in parts):
            continue
        if has_arabic(gram):
            for v in arabic_variants(gram):
                if v in vocab.brands:
                    ent.medicines.append(MedicineMention(gram, vocab.brands[v], 100.0, "alias"))
                    take(i, n)
                    break
                sk = skeleton_arabic(v)
                if len(sk) >= 4 and sk in vocab.brand_skeletons:
                    ent.medicines.append(MedicineMention(gram, vocab.brand_skeletons[sk], 85.0, "arabic_skeleton"))
                    take(i, n)
                    break
            continue
        if gram in vocab.brands:
            ent.medicines.append(MedicineMention(gram, vocab.brands[gram], 100.0, "exact"))
            take(i, n)
            continue
        if n == 1 and gram in TRIGGER_TOKENS:
            continue
        if len(gram.replace(" ", "")) >= 4:
            best = max(vocab.brands, key=lambda b: fuzz.ratio(gram, b), default=None)
            score = fuzz.ratio(gram, best) if best else 0
            if best and score >= (82 if len(gram) >= 6 else 88):
                ent.medicines.append(MedicineMention(gram, vocab.brands[best], round(score, 1), "fuzzy"))
                take(i, n)

    # 3. dosage : de préférence juste après le nom reconnu
    after: list[str] = []
    if used:
        after = tokens[max(used) + 1:max(used) + 2]
    ent.dose = extract_dose(norm, after)
    # dédoublonnage : une même marque citée deux fois
    seen: set[str] = set()
    ent.medicines = [x for x in ent.medicines if not (x.brand in seen or seen.add(x.brand))]
    return ent
