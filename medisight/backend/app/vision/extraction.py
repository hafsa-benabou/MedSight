"""Extraction des informations pharmaceutiques depuis les lignes OCR : nom commercial (segments candidats), dosages,
concentrations, substances, forme, conditionnement, laboratoire, chiffres imprimés sous le code-barres.

Règles : un dosage n'est jamais corrigé (« 5OO MG » reste illisible, pas « 500 MG ») ; une concentration
(« 80 MG / ML ») n'est jamais lue comme une dose ; un volume de conditionnement (« FLACON DE 60 ML ») n'est pas un dosage."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from decimal import Decimal

from rapidfuzz import fuzz

from app.core.ean import normalize_ean
from app.ingestion.common import PACK_UNITS, canonical_form
from app.nlp.text import normalize_text

_MASS = {"mg": Decimal(1), "g": Decimal(1000), "µg": Decimal("0.001"), "mcg": Decimal("0.001"), "ug": Decimal("0.001")}
_UNITS = r"mg|g|µg|mcg|ug|ml|ui|mui|mmol|meq|mbq|gbq|%"
# Dénominateur = volume ou prise (« 80 mg / ml », « 20 mg / g », « 100 µg / dose ») : concentration.
# « 1 g / 125 mg » n'a pas de dénominateur valide : deux dosages distincts (association de substances).
_DOSE_RE = re.compile(rf"(?<![\w.])(\d+(?:\.\d+)?) ?({_UNITS})(?: / (\d+(?:\.\d+)?)? ?(ml|l|g|doses?)(?![a-zµ]))?(?![a-zµ])")
_CONTAINERS = r"boites?|etuis?|flacons?|tubes?|plaquettes?|pots?|sachets?|ampoules?"
_PACK_OF = re.compile(rf"\b(?:{_CONTAINERS}) (?:de |d un |dun )?(\d+(?:\.\d+)?) ?([a-z]+)?")
_PACK_COUNT = re.compile(r"(?<![\w.])(\d{1,4}) ?(comprimes?|cp|gelules?|sachets?|capsules?|ampoules?|suppositoires?|"
                         r"doses|unidoses|stylos?|seringues?|flacons?)\b")
_DIGITS13 = re.compile(r"(?<!\d)(\d[\d ]{11,17}\d)(?!\d)")
_LAB_HINT = re.compile(r"\b(laboratoires?|labs?|pharma|pharmaceuticals?|sante|healthcare)\b")


@dataclass
class Dose:
    raw: str
    value: float
    unit: str
    mg: float | None = None
    per: str | None = None  # dénominateur d'une concentration (« ml », « dose ») ; None pour une dose unitaire

    @property
    def is_concentration(self) -> bool:
        return self.per is not None


@dataclass
class Extracted:
    brand_segments: list[str] = field(default_factory=list)  # du plus grand texte au plus petit
    doses: list[Dose] = field(default_factory=list)
    dosage_text: str | None = None  # dosage composé tel qu'imprimé (« 1 g / 125 mg »)
    substances: list[dict] = field(default_factory=list)  # {"id", "name", "matched"}
    form: str | None = None  # forme canonique
    form_text: str | None = None
    pack_quantity: float | None = None
    pack_unit: str | None = None
    pack_text: str | None = None
    laboratory: str | None = None
    printed_codes: list[dict] = field(default_factory=list)  # chiffres lus par OCR (indice, jamais corrigés)

    def summary(self) -> dict:
        out = asdict(self)
        out["doses"] = [{"text": d.raw, "value": d.value, "unit": d.unit, "mg": d.mg,
                         "concentration": d.is_concentration} for d in self.doses]
        return out

    @property
    def has_evidence(self) -> bool:
        return bool(self.brand_segments or self.doses or self.substances)


@dataclass
class Vocabulary:
    """Termes connus de la base : substances (nom, synonymes, termes de recherche) et laboratoires."""
    substances: dict[str, tuple[int, str]] = field(default_factory=dict)  # terme normalisé -> (id, nom)
    laboratories: dict[str, str] = field(default_factory=dict)  # nom normalisé -> nom


def _dose(match: re.Match) -> Dose:
    value, unit, per_value, per_unit = match.groups()
    v = Decimal(value)
    per = f"{per_value} {per_unit}" if per_value else per_unit
    mg = float(v * _MASS[unit]) if unit in _MASS and per_unit is None else None  # concentration : pas de masse
    return Dose(match.group(0).strip(), float(v), unit, mg, per)


def _find_terms(text: str, lines: list[str], terms: dict[str, tuple[int, str]]) -> list[dict]:
    found: dict[int, dict] = {}
    padded = f" {text} "
    for term, (iid, name) in terms.items():
        if len(term) < 4:
            continue
        if f" {term} " in padded:
            found.setdefault(iid, {"id": iid, "name": name, "matched": term, "method": "exact"})
    for term, (iid, name) in terms.items():  # tolérance aux fautes OCR, mots longs seulement
        if iid in found or len(term) < 7:
            continue
        for line in lines:
            if fuzz.partial_ratio(term, line) >= 92 and abs(len(line) - len(term)) <= max(12, len(term)):
                found[iid] = {"id": iid, "name": name, "matched": term, "method": "fuzzy"}
                break
    return list(found.values())


def extract(lines: list[tuple[str, int]], vocab: Vocabulary | None = None) -> Extracted:
    """`lines` : (texte OCR, hauteur en pixels). La hauteur sert à placer en tête les plus grands textes (le nom)."""
    vocab = vocab or Vocabulary()
    norm = [(normalize_text(t), h) for t, h in lines if t and t.strip()]
    norm = [(t, h) for t, h in norm if t]
    full = " \n ".join(t for t, _ in norm)
    out = Extracted()

    pack_spans = []
    for line, _ in norm:
        m_of = _PACK_OF.search(line)
        if m_of and (m_of.group(2) is None or normalize_text(m_of.group(2)) in PACK_UNITS):
            out.pack_quantity, out.pack_unit = float(m_of.group(1)), PACK_UNITS.get(normalize_text(m_of.group(2) or ""))
            out.pack_text = m_of.group(0)
            pack_spans.append(m_of.group(0))
            break
    if out.pack_quantity is None:
        for line, _ in norm:
            m_count = _PACK_COUNT.search(line)
            if m_count:
                out.pack_quantity, out.pack_unit = float(m_count.group(1)), PACK_UNITS.get(m_count.group(2))
                out.pack_text = m_count.group(0)
                pack_spans.append(m_count.group(0))
                break

    for line, _ in norm:
        stripped = line
        for span in pack_spans:
            stripped = stripped.replace(span, " ")
        for m in _DOSE_RE.finditer(stripped):
            d = _dose(m)
            if d.raw not in {x.raw for x in out.doses}:
                out.doses.append(d)
        combo = re.search(rf"\d+(?:\.\d+)? ?(?:mg|g|µg|mcg)(?: / \d+(?:\.\d+)? ?(?:mg|g|µg|mcg))+", stripped)
        if combo and out.dosage_text is None:
            out.dosage_text = combo.group(0)
    if out.dosage_text is None and out.doses:
        out.dosage_text = out.doses[0].raw

    out.substances = _find_terms(full, [t for t, _ in norm], vocab.substances)
    form = canonical_form(full)
    out.form = None if form in (None, "autre") else form
    if out.form:
        out.form_text = next((t for t, _ in norm if canonical_form(t) == out.form), None)
    for lab_norm, lab in vocab.laboratories.items():
        if len(lab_norm) >= 4 and f" {lab_norm} " in f" {full} ":
            out.laboratory = lab
            break
    if out.laboratory is None:
        out.laboratory = next((t for t, _ in norm if _LAB_HINT.search(t)), None)

    for m in _DIGITS13.finditer(full.replace("\n", " ")):
        digits = re.sub(r"\D", "", m.group(1))
        if len(digits) in (13, 14):
            code, status = normalize_ean(digits)
            out.printed_codes.append({"code": code, "status": status})

    known = {s["matched"] for s in out.substances}
    for line, _h in sorted(norm, key=lambda x: -x[1]):
        seg = line
        for span in pack_spans:
            seg = seg.replace(span, " ")
        seg = _DIGITS13.sub(" ", _DOSE_RE.sub(" ", seg))
        for term in known:
            seg = seg.replace(term, " ")
        seg = re.sub(r"\s+", " ", re.sub(r"[^\w\s\-]", " ", seg)).strip()
        if sum(c.isalpha() for c in seg) >= 3 and seg not in out.brand_segments:
            out.brand_segments.append(seg)
    out.brand_segments = out.brand_segments[:12]
    return out
