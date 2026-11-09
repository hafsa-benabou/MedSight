"""Rapprochement des indices extraits d'une photo avec le catalogue PostgreSQL (présentations marocaines).

Chaque présentation candidate reçoit des indices : code-barres, marque, dosage, substance, forme, conditionnement,
chacun « concordant » (match), « contradictoire » (conflict) ou « inconnu ». L'indice de correspondance (0-100)
est une somme pondérée **heuristique** de ces indices : il sert à classer et à expliquer, ce n'est ni une
probabilité ni une précision mesurée.

Règles de sécurité appliquées :
1. un dosage contradictoire élimine le candidat (jamais de substitution silencieuse) ; les dosages disponibles
   sont renvoyés à part ;
2. une concentration n'est comparée qu'à une concentration (strengths_equivalent) ;
3. un conditionnement différent est un indice contradictoire, deux conditionnements possibles restent tous deux listés ;
4. un nom approximatif seul ne suffit jamais à identifier ;
5. seules les fiches du marché marocain sont candidates, et jamais les données simulées (sauf option de démo) ;
6. un code-barres contredit par le texte donne un résultat « contradictoire », pas une identification."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from rapidfuzz import fuzz
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app import models as m
from app.ingestion.common import strengths_equivalent
from app.nlp.text import normalize_text
from app.services.catalog import source_ref
from app.vision.barcodes import BarcodeRead
from app.vision.extraction import Extracted, Vocabulary

WEIGHTS = {"barcode": 45, "brand": 30, "dosage": 15, "substance": 10, "form": 5, "pack": 5}
PENALTIES = {"barcode": -35, "dosage": -40, "substance": -30, "form": -10, "pack": -10}
BRAND_MIN = 80  # similarité minimale (0-100) pour retenir un nom
BRAND_STRONG = 90
AMBIGUITY_GAP = 10  # écart minimal entre deux spécialités pour en désigner une


@dataclass
class Evidence:
    barcode: str = "unknown"
    brand: float = 0.0
    brand_matched: str | None = None
    dosage: str = "unknown"
    substance: str = "unknown"
    form: str = "unknown"
    pack: str = "unknown"
    laboratory: str = "unknown"  # affiché seulement : n'entre ni dans le score ni dans conflicts()

    def conflicts(self) -> list[str]:
        return [k for k in ("barcode", "dosage", "substance", "form", "pack") if getattr(self, k) == "conflict"]

    def score(self) -> float:
        s = 0.0
        for k in ("barcode", "dosage", "substance", "form", "pack"):
            v = getattr(self, k)
            s += WEIGHTS[k] if v == "match" else PENALTIES[k] if v == "conflict" else 0
        if self.brand >= BRAND_MIN:
            s += 10 + (WEIGHTS["brand"] - 10) * (self.brand - BRAND_MIN) / (100 - BRAND_MIN)
        return max(0.0, min(100.0, round(s, 1)))


@dataclass
class Candidate:
    medicine: m.Medicine
    presentation: m.MedicinePresentation
    evidence: Evidence
    via: set[str] = field(default_factory=set)

    @property
    def score(self) -> float:
        return self.evidence.score()


def load_vocabulary(db: Session) -> Vocabulary:
    vocab = Vocabulary()
    for ing in db.scalars(select(m.ActiveIngredient)):
        for term in [ing.name, *(ing.synonyms or []), *(ing.search_terms or [])]:
            t = normalize_text(term)
            if t:
                vocab.substances.setdefault(t, (ing.id, ing.name))
    for lab in db.scalars(select(m.Laboratory)):
        vocab.laboratories[lab.name_normalized] = lab.name
    return vocab


def _catalog_query(include_simulated: bool):
    stmt = (select(m.Medicine).join(m.DataSource, m.Medicine.source_id == m.DataSource.id)
            .where(or_(m.DataSource.market.is_(None), m.DataSource.market == "MA"))
            .options(selectinload(m.Medicine.ingredients).selectinload(m.MedicineIngredient.ingredient),
                     selectinload(m.Medicine.presentations).selectinload(m.MedicinePresentation.source),
                     selectinload(m.Medicine.form), selectinload(m.Medicine.aliases),
                     selectinload(m.Medicine.laboratory), selectinload(m.Medicine.source)))
    if not include_simulated:
        stmt = stmt.where(m.Medicine.data_status != "simulated")
    return stmt


def brand_similarity(segments: list[str], med: m.Medicine) -> tuple[float, str | None]:
    """Meilleure similarité entre les textes lus et le nom (ou une variante sourcée) ; fenêtres de mots de même
    longueur que le nom, pour qu'un nom court ne soit pas « trouvé » dans une longue phrase."""
    names = [med.brand_normalized] + [a.alias_normalized for a in med.aliases if a.data_status != "simulated"]
    best, best_name = 0.0, None
    for name in names:
        n = len(name.split())
        for seg in segments:
            tokens = seg.split()
            windows = {" ".join(tokens[i:i + k]) for k in {max(1, n - 1), n, n + 1} for i in range(len(tokens) - k + 1)}
            for w in windows or {seg}:
                if len(name) <= 3 and w != name:
                    continue  # nom très court : égalité stricte seulement
                r = fuzz.ratio(w, name)
                if r > best:
                    best, best_name = r, name
    return best, best_name


def _dosage_evidence(ex: Extracted, med: m.Medicine) -> str:
    if not ex.doses or not med.dosage_text:
        return "unknown"
    raws = [d.raw for d in ex.doses] + ([ex.dosage_text] if ex.dosage_text else [])
    if any(strengths_equivalent(raw, med.dosage_text) is True for raw in raws):
        return "match"
    # association : chaque substance dosée doit retrouver son dosage parmi les doses lues
    strengths = [mi.strength_text for mi in med.ingredients if mi.strength_text]
    if len(strengths) > 1 and all(any(strengths_equivalent(d.raw, st) is True for d in ex.doses) for st in strengths):
        return "match"
    comparable = [raw for raw in raws if strengths_equivalent(raw, med.dosage_text) is not None]
    return "conflict" if comparable else "unknown"


def _substance_evidence(ex: Extracted, med: m.Medicine) -> str:
    if not ex.substances or not med.ingredients:
        return "unknown"
    seen = {s["id"] for s in ex.substances}
    own = {mi.ingredient_id for mi in med.ingredients}
    if own <= seen:
        return "match"
    return "conflict" if not (own & seen) else "unknown"


def _form_evidence(ex: Extracted, med: m.Medicine) -> str:
    own = med.form.canonical if med.form else None
    if not ex.form or not own:
        return "unknown"
    if ex.form == own:
        return "match"
    # « comprimé » lu sur une boîte de comprimés effervescents ou pelliculés : compatible, pas contradictoire
    if ex.form == "comprime" and own.startswith("comprime"):
        return "unknown"
    # « capsules » (anglais, néerlandais…) imprimé sur une boîte de gélules : même forme, pas une contradiction
    if {ex.form, own} == {"gelule", "capsule"}:
        return "unknown"
    return "conflict"


_LAB_GENERIC = {"laboratoire", "laboratoires", "labo", "lab", "labs", "pharma", "pharmaceutical", "pharmaceuticals",
                "pharmaceutique", "pharmaceutiques", "sante", "healthcare", "maroc", "morocco", "sa", "sarl", "ltd", "inc"}


def _lab_evidence(ex: Extracted, med: m.Medicine) -> str:
    """Laboratoire lu sur la photo comparé à celui du catalogue. Indice affiché, non compté dans l'indice de
    correspondance : un titulaire différent peut être légitime (transfert d'AMM, boîte d'un autre pays)."""
    if not ex.laboratory or not med.laboratory:
        return "unknown"
    read = {w for w in normalize_text(ex.laboratory).split() if len(w) >= 3 and w not in _LAB_GENERIC}
    own = {w for w in normalize_text(med.laboratory.name).split() if len(w) >= 3 and w not in _LAB_GENERIC}
    if not read or not own:
        return "unknown"
    if any(fuzz.ratio(a, b) >= 85 for a in read for b in own):
        return "match"
    return "conflict"


def _pack_evidence(ex: Extracted, pres: m.MedicinePresentation) -> str:
    if ex.pack_quantity is None or pres.pack_quantity is None:
        return "unknown"
    same_qty = Decimal(str(ex.pack_quantity)) == pres.pack_quantity
    same_unit = ex.pack_unit is None or pres.pack_unit is None or ex.pack_unit == pres.pack_unit
    return "match" if same_qty and same_unit else "conflict"


def explain(c: Candidate) -> list[str]:
    e, out = c.evidence, []
    labels = {"match": "concordant", "conflict": "CONTRADICTOIRE"}
    if e.barcode != "unknown":
        out.append(f"Code-barres : {labels[e.barcode]}")
    if e.brand >= BRAND_MIN:
        out.append(f"Nom lu proche de « {e.brand_matched} » (similarité {e.brand:.0f}/100)")
    for key, label in (("dosage", "Dosage"), ("substance", "Substance active"), ("form", "Forme"),
                       ("pack", "Conditionnement")):
        v = getattr(e, key)
        out.append(f"{label} : {labels.get(v, 'non lu ou non comparable')}")
    if e.laboratory != "unknown":
        out.append("Laboratoire : " + ("concordant" if e.laboratory == "match"
                                       else "DIFFÉRENT de la fiche (à vérifier, non compté dans l'indice)"))
    return out


def candidate_out(c: Candidate, rank: int) -> dict:
    med, pres = c.medicine, c.presentation
    return {
        "rank": rank, "score": c.score, "medicine_id": med.id, "presentation_id": pres.id, "brand": med.brand_name,
        "dosage": med.dosage_text, "form": med.form.label if med.form else None,
        "presentation": pres.label, "ean13": pres.ean13, "ppv": float(pres.ppv_mad) if pres.ppv_mad is not None else None,
        "price_as_of": pres.price_as_of.isoformat() if pres.price_as_of else None,
        "ingredients": [{"name": mi.ingredient.name, "strength": mi.strength_text} for mi in med.ingredients],
        "laboratory": med.laboratory.name if med.laboratory else None, "data_status": pres.data_status,
        "source": source_ref(pres.source), "medicine_source": source_ref(med.source),
        "evidence": {"barcode": c.evidence.barcode, "brand_similarity": round(c.evidence.brand, 1),
                     "dosage": c.evidence.dosage, "substance": c.evidence.substance, "form": c.evidence.form,
                     "pack": c.evidence.pack, "laboratory": c.evidence.laboratory},
        "found_by": sorted(c.via), "explanation": explain(c),
    }


@dataclass
class MatchResult:
    status: str
    reliability: str
    level: str | None
    candidates: list[Candidate]
    reasons: list[str]
    warnings: list[str]
    available_dosages: list[str] = field(default_factory=list)
    barcode_catalog: dict[str, bool] = field(default_factory=dict)


def match(db: Session, ex: Extracted, barcodes: list[BarcodeRead], *, include_simulated: bool = False) -> MatchResult:
    warnings: list[str] = []
    reasons: list[str] = []
    valid_codes = {b.code for b in barcodes if b.status == "valid" and b.code}
    for b in barcodes:
        if b.status == "gtin14":
            warnings.append(f"GTIN-14 logistique {b.code} : ne désigne pas une boîte, non utilisé")
        elif b.status != "valid":
            warnings.append(f"Code-barres {b.code or b.raw} lu mais invalide ({b.status}) : non utilisé, jamais corrigé")
    printed = {p["code"] for p in ex.printed_codes if p["status"] == "valid"}
    for p in ex.printed_codes:
        if p["status"] != "valid":
            warnings.append(f"Chiffres {p['code']} lus par OCR : clé de contrôle invalide, ignorés")

    meds = list(db.scalars(_catalog_query(include_simulated)).unique())
    by_code: dict[str, list[tuple[m.Medicine, m.MedicinePresentation]]] = {}
    for med in meds:
        for pres in med.presentations:
            if pres.ean13 and (include_simulated or pres.data_status != "simulated"):
                by_code.setdefault(pres.ean13, []).append((med, pres))
    barcode_catalog = {code: code in by_code for code in valid_codes}
    known_codes = {code for code, known in barcode_catalog.items() if known}
    for code, known in barcode_catalog.items():
        if not known:
            warnings.append(f"Code-barres {code} valide mais absent du catalogue : identification poursuivie par le texte")
    for code in printed - valid_codes:
        if code in by_code:
            warnings.append(f"Chiffres {code} lus par OCR sous le code-barres : utilisés comme indice faible seulement")

    candidates: dict[int, Candidate] = {}
    brand_hits: dict[int, tuple[float, str | None]] = {}
    for med in meds:
        sim, name = brand_similarity(ex.brand_segments, med) if ex.brand_segments else (0.0, None)
        brand_hits[med.id] = (sim, name)
    for med in meds:
        sim, name = brand_hits[med.id]
        via = set()
        if any(p.ean13 in valid_codes for p in med.presentations if p.ean13):
            via.add("barcode")
        if sim >= BRAND_MIN:
            via.add("brand")
        if not via and ex.substances and med.ingredients and \
                {mi.ingredient_id for mi in med.ingredients} <= {s["id"] for s in ex.substances}:
            via.add("substance")
        if not via:
            continue
        dosage, substance, form = _dosage_evidence(ex, med), _substance_evidence(ex, med), _form_evidence(ex, med)
        for pres in med.presentations:
            if pres.data_status == "simulated" and not include_simulated:
                continue
            if known_codes and pres.ean13:
                # contradiction seulement si le code lu désigne une AUTRE présentation du catalogue ;
                # un code valide inconnu du catalogue (lacune de données) ne contredit rien
                bc = "match" if pres.ean13 in known_codes else "conflict"
            else:
                bc = "unknown"  # y compris chiffres lus par OCR : pas assez sûrs pour valoir un code-barres lu
            ev = Evidence(bc, sim, name, dosage, substance, form, _pack_evidence(ex, pres), _lab_evidence(ex, med))
            candidates[pres.id] = Candidate(med, pres, ev, set(via))

    # Règle 1 : un dosage contradictoire élimine le candidat (sauf s'il a été trouvé par code-barres : contradiction)
    dosage_rejected = [c for c in candidates.values() if c.evidence.dosage == "conflict" and c.evidence.barcode != "match"]
    pool = [c for c in candidates.values() if c not in dosage_rejected]
    # nom seul ou composition seule, très faible : écarté du classement
    pool = [c for c in pool if c.score >= 20 or "barcode" in c.via]
    pool.sort(key=lambda c: (-c.score, c.medicine.brand_normalized, c.presentation.id))
    # le dosage lu n'est « absent » que pour les marques dont aucune autre fiche ne le porte (ex. AMLOR 10 MG écarté
    # alors qu'AMLOR 5 MG est retenu : ne pas annoncer « 5 mg absent pour AMLOR »)
    kept_brands = {c.medicine.brand_normalized for c in pool}
    absent = [c for c in dosage_rejected if c.medicine.brand_normalized not in kept_brands]
    if absent:
        avail = sorted({c.medicine.dosage_text for c in absent if c.medicine.dosage_text})
        names = sorted({c.medicine.brand_name for c in absent})
        reasons.append(f"Dosage lu ({ex.dosage_text}) absent du catalogue pour {', '.join(names)} : "
                       f"aucune autre dose n'est proposée à sa place")
    else:
        avail = []

    if not pool:
        status = "not_found"
        if not ex.has_evidence and not valid_codes:
            reasons.append("Aucun nom, dosage ou code-barres exploitable n'a été lu")
        elif not avail:
            reasons.append("Aucune présentation du catalogue ne correspond aux indices lus")
        return MatchResult(status, "none", None, [], reasons, warnings, avail, barcode_catalog)

    top = pool[0]
    e = top.evidence
    strong_other = [c for c in pool if c.medicine.id != top.medicine.id and c.evidence.brand >= BRAND_STRONG
                    and "brand" in c.via]
    if e.barcode == "match" and (e.conflicts() or (strong_other and e.brand < BRAND_MIN)):
        what = ", ".join(e.conflicts()) or "nom lu"
        reasons.append(f"Le code-barres désigne {top.medicine.brand_name} {top.medicine.dosage_text or ''} "
                       f"mais le texte lu le contredit ({what})")
        return MatchResult("contradictory", "low", None, pool[:3], reasons, warnings, avail, barcode_catalog)

    if e.form == "conflict" and top.medicine.form:
        reasons.append(f"Forme lue sur la photo (« {ex.form_text or ex.form} ») différente de celle de la fiche du "
                       f"catalogue ({top.medicine.form.label}) : il peut s'agir d'une autre présentation, non référencée")
    if e.pack == "conflict":
        reasons.append(f"Conditionnement lu sur la photo (« {ex.pack_text} ») différent de « {top.presentation.label} »")
    corroborations = sum([e.brand >= 85, e.dosage == "match", e.substance == "match"])
    text_evidence = ex.has_evidence
    identified, reliability = False, "low"
    if not e.conflicts():
        if e.barcode == "match" and corroborations >= 1:
            identified, reliability = True, "high"
        elif e.barcode == "match" and not text_evidence:
            identified, reliability = True, "medium"
            warnings.append("Identification par le seul code-barres, non corroborée par le texte de la boîte")
        elif e.brand >= BRAND_STRONG and e.dosage == "match":
            extra = sum([e.form == "match", e.pack == "match", e.substance == "match"])
            identified, reliability = True, "high" if extra >= 1 else "medium"
            if e.form == "unknown":
                form = top.medicine.form.label if top.medicine.form else "non renseignée"
                lab = top.medicine.laboratory.name if top.medicine.laboratory else "non renseigné"
                warnings.append(f"Forme pharmaceutique non lue sur la photo : vérifiez sur la boîte qu'il s'agit bien de "
                                f"la forme « {form} » (laboratoire {lab}) ; une boîte d'un autre pays ou d'une autre "
                                f"forme peut porter le même nom.")
    if e.laboratory == "conflict" and top.medicine.laboratory:
        warnings.append(f"Laboratoire lu sur la photo (« {ex.laboratory} ») différent de celui de la fiche "
                        f"({top.medicine.laboratory.name}) : boîte possiblement d'un autre pays ou d'un autre titulaire, "
                        f"à vérifier.")
    if not identified:
        if e.brand >= BRAND_MIN and e.dosage == "unknown":
            reasons.append("Nom reconnu mais dosage non lu : plusieurs dosages restent possibles")
        elif e.brand < BRAND_MIN and e.barcode != "match":
            reasons.append("Aucun nom commercial reconnu avec certitude")
        weak_single = len(pool) == 1 and top.score < 30
        return MatchResult("not_found" if weak_single else "ambiguous", "low", None, pool[:3], reasons, warnings,
                           avail, barcode_catalog)

    rivals = [c for c in pool[1:] if c.medicine.id != top.medicine.id and c.score >= top.score - AMBIGUITY_GAP]
    if rivals:
        reasons.append("Plusieurs spécialités correspondent presque aussi bien aux indices lus")
        return MatchResult("ambiguous", "low", None, pool[:3], reasons, warnings, avail, barcode_catalog)
    siblings = [c for c in pool[1:] if c.medicine.id == top.medicine.id and abs(c.score - top.score) < 1e-6]
    agreeing = [label for key, label in (("barcode", "code-barres lu"), ("dosage", "dosage"), ("substance", "substance"),
                                         ("form", "forme"), ("pack", "conditionnement"))
                if getattr(e, key) == "match"]
    if e.brand >= BRAND_MIN:
        agreeing.insert(0, "nom")
    if siblings:
        group = [top, *siblings][:3]
        reasons.append(f"Le nom {top.medicine.brand_name} et le dosage {top.medicine.dosage_text or ''} ont été reconnus. "
                       f"Le conditionnement n'a pas été suffisamment identifié pour distinguer les {len(siblings) + 1} "
                       f"présentations disponibles ({', '.join(c.presentation.label for c in group)}) : toutes sont "
                       "listées, aucune n'est retenue à la place des autres.")
        reasons.append("Pour les départager : le code-barres de la boîte, ou le nombre d'unités imprimé "
                       "(ex. « 28 comprimés »), lisible sur la photo.")
        return MatchResult("identified", reliability, "medicine", group, reasons, warnings, avail, barcode_catalog)
    reasons.append("Indices concordants, sans contradiction : " + ", ".join(agreeing))
    return MatchResult("identified", reliability, "presentation", pool[:3], reasons, warnings, avail, barcode_catalog)
