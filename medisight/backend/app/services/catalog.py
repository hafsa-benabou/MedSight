"""Recherche et fiches médicaments : tolérance aux fautes, dosage jamais substitué, provenance exposée."""
from __future__ import annotations

import re
from decimal import Decimal

from rapidfuzz import fuzz
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app import models as m
from app.core.ean import normalize_ean
from app.nlp.text import normalize_text

_BARCODE = re.compile(r"^\s*\d[\d\s]{11,16}\d\s*$")
_DOSE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(mg|g|mcg|µg|ug)\b")
_MASS = {"mg": Decimal(1), "g": Decimal(1000), "mcg": Decimal("0.001"), "µg": Decimal("0.001"), "ug": Decimal("0.001")}
_LOAD = (selectinload(m.Medicine.ingredients).selectinload(m.MedicineIngredient.ingredient),
         selectinload(m.Medicine.presentations).selectinload(m.MedicinePresentation.source),
         selectinload(m.Medicine.form), selectinload(m.Medicine.laboratory), selectinload(m.Medicine.source))
STOCK_NOTICE = "Stock non vérifié — contactez la pharmacie pour confirmer la disponibilité."


def source_ref(src: m.DataSource | None) -> dict | None:
    if src is None:
        return None
    return {"code": src.code, "name": src.name, "url": src.url, "license": src.license, "market": src.market}


def _num(v) -> float | None:
    return float(v) if v is not None else None


def presentation_out(p: m.MedicinePresentation) -> dict:
    return {"id": p.id, "label": p.label, "ppv": _num(p.ppv_mad), "ph": _num(p.ph_mad), "price_status": p.price_status,
            "price_as_of": p.price_as_of.isoformat() if p.price_as_of else None, "ean13": p.ean13,
            "pack_quantity": _num(p.pack_quantity), "pack_unit": p.pack_unit,
            "data_status": p.data_status, "source": source_ref(p.source)}


def medicine_card(med: m.Medicine) -> dict:
    # une fiche réelle n'affiche jamais un prix « à partir de » issu d'une présentation simulée
    prices = [p.ppv_mad for p in med.presentations if p.ppv_mad is not None
              and (p.data_status != "simulated" or med.data_status == "simulated")]
    return {
        "id": med.id, "brand": med.brand_name, "dosage": med.dosage_text,
        "form": med.form.label if med.form else None, "form_canonical": med.form.canonical if med.form else None,
        "laboratory": med.laboratory.name if med.laboratory else None,
        "ingredients": [{"name": mi.ingredient.name, "strength": mi.strength_text} for mi in med.ingredients],
        "princeps_status": med.princeps_status, "marketing_status": med.marketing_status, "is_marketed": med.is_marketed,
        "data_status": med.data_status, "source": source_ref(med.source), "min_ppv": _num(min(prices)) if prices else None,
        "presentations": [presentation_out(p) for p in med.presentations],
    }


def _dose_mg(value: str, unit: str) -> Decimal:
    return Decimal(value) * _MASS[unit]


def _search_by_barcode(db: Session, q: str, page: int, size: int) -> dict:
    """Code-barres saisi ou lu (EAN-13, ou GTIN-14 d'un DataMatrix) : correspondance exacte uniquement."""
    code, status = normalize_ean(q)
    meta = {"query_normalized": code, "matched_by": "barcode", "ean_status": status, "dosage_requested": None,
            "dosage_found": None, "available_dosages": [], "matched_presentation_ids": []}
    if status != "valid":  # un code invalide n'est jamais « corrigé » vers un code voisin
        return {"items": [], "total": 0, "page": page, "size": size, "meta": meta}
    pres_ids = list(db.scalars(select(m.MedicinePresentation.id).where(m.MedicinePresentation.ean13 == code)))
    med_ids = set(db.scalars(select(m.MedicinePresentation.medicine_id).where(m.MedicinePresentation.ean13 == code)))
    med_ids |= {i for i in db.scalars(select(m.GenericGroupMember.medicine_id).where(
        m.GenericGroupMember.ean13 == code, m.GenericGroupMember.ean_status == "valid")) if i is not None}
    meds = list(db.scalars(select(m.Medicine).options(*_LOAD).where(m.Medicine.id.in_(med_ids))
                           .order_by(m.Medicine.brand_normalized)).unique()) if med_ids else []
    meta["matched_presentation_ids"] = pres_ids
    items = [medicine_card(x) for x in meds[(page - 1) * size: page * size]]
    return {"items": items, "total": len(meds), "page": page, "size": size, "meta": meta}


def search_medicines(db: Session, q: str = "", *, form: str | None = None, status: str | None = None,
                     page: int = 1, size: int = 20) -> dict:
    if _BARCODE.match(q or "") and len(re.sub(r"\D", "", q)) in (13, 14):
        return _search_by_barcode(db, q, page, size)
    norm = normalize_text(q)
    dose = _DOSE.search(norm)
    dose_mg = _dose_mg(dose.group(1), dose.group(2)) if dose else None
    text = _DOSE.sub(" ", norm).strip()
    stmt = select(m.Medicine).options(*_LOAD)
    if status:
        stmt = stmt.where(m.Medicine.data_status == status)
    if form:
        stmt = stmt.join(m.PharmaceuticalForm).where(m.PharmaceuticalForm.canonical == form)
    if text:
        cond = m.Medicine.search_text.ilike(f"%{text}%")
        if db.bind.dialect.name == "postgresql":
            cond = or_(cond, func.word_similarity(text, m.Medicine.search_text) > 0.35)
        stmt = stmt.where(cond).limit(400)
    else:
        stmt = stmt.order_by(m.Medicine.brand_normalized, m.Medicine.dosage_text)
    meds = list(db.scalars(stmt).unique())
    scored = []
    for med in meds:
        score = 100.0 if not text else max(fuzz.ratio(text, med.brand_normalized),
                                           fuzz.partial_ratio(text, med.search_text) * 0.92)
        scored.append((score, med))
    scored = [s for s in scored if s[0] >= 60] if text else scored
    meta = {"query_normalized": norm, "matched_by": "text", "dosage_requested": f"{dose.group(1)} {dose.group(2)}" if dose else None,
            "dosage_found": None, "available_dosages": []}
    if dose_mg is not None and scored:
        with_dose = [s for s in scored if any(mi.strength_mg == dose_mg for mi in s[1].ingredients)]
        meta["dosage_found"] = bool(with_dose)
        if not with_dose:  # le dosage demandé n'existe pas : on ne le remplace jamais par un autre
            meta["available_dosages"] = sorted({s[1].dosage_text for s in scored if s[1].dosage_text})
        scored = with_dose
    scored.sort(key=lambda s: (-s[0], s[1].brand_normalized, s[1].dosage_text or ""))
    if text and scored and scored[0][0] < 95:
        meta["did_you_mean"] = scored[0][1].brand_name
    total = len(scored)
    items = [medicine_card(med) for _, med in scored[(page - 1) * size: page * size]]
    return {"items": items, "total": total, "page": page, "size": size, "meta": meta}


def autocomplete(db: Session, q: str, limit: int = 8) -> list[dict]:
    res = search_medicines(db, q, size=limit)
    return [{"id": c["id"], "label": f"{c['brand']} {c['dosage'] or ''}".strip(), "form": c["form"],
             "data_status": c["data_status"]} for c in res["items"]]


def medicine_detail(db: Session, medicine_id: int) -> dict | None:
    med = db.scalar(select(m.Medicine).options(*_LOAD).where(m.Medicine.id == medicine_id))
    if med is None:
        return None
    card = medicine_card(med)
    reimb = db.scalars(select(m.Reimbursement).options(selectinload(m.Reimbursement.source))
                       .where(m.Reimbursement.medicine_id == med.id)).all()
    sections = db.scalars(select(m.ClinicalSection).options(selectinload(m.ClinicalSection.source))
                          .where(m.ClinicalSection.medicine_id == med.id)).all()
    card.update({
        "amm_status": med.amm_status, "atc_code": med.atc_code, "rcp_url": med.rcp_url,
        "therapeutic_class": med.therapeutic_class.name if med.therapeutic_class else None,
        "reimbursements": [{"presentation_id": r.presentation_id, "base": _num(r.base_remboursement_mad),
                            "rate": _num(r.taux_remboursement), "valid_as_of": r.valid_as_of.isoformat() if r.valid_as_of else None,
                            "ppv_reference": _num(r.ppv_reference_mad), "data_status": r.data_status,
                            "source": source_ref(r.source)} for r in reimb],
        "clinical_sections": [{"code": s.section_code, "title": s.title, "content": s.content, "source": source_ref(s.source),
                               "source_url": s.source_url, "document_date": s.document_date.isoformat() if s.document_date else None,
                               "data_status": s.data_status} for s in sections],
    })
    return card


def _signature(med: m.Medicine) -> frozenset:
    return frozenset((mi.ingredient_id, mi.strength_mg if mi.strength_mg is not None else normalize_text(mi.strength_text or ""))
                     for mi in med.ingredients)


def generics_for(db: Session, medicine_id: int) -> dict | None:
    med = db.scalar(select(m.Medicine).options(*_LOAD).where(m.Medicine.id == medicine_id))
    if med is None:
        return None
    regulatory = []
    member_rows = db.scalars(select(m.GenericGroupMember).where(m.GenericGroupMember.medicine_id == med.id)).all()
    for group_id in {r.group_id for r in member_rows}:
        g = db.scalar(select(m.GenericGroup).options(selectinload(m.GenericGroup.members), selectinload(m.GenericGroup.source))
                      .where(m.GenericGroup.id == group_id))
        regulatory.append({"group": g.label, "route": g.route, "edition": g.register_edition, "data_status": g.data_status,
                           "source": source_ref(g.source),
                           "members": [{"type": x.member_type, "label": x.raw_label, "laboratory": x.laboratory_raw,
                                        "ean13": x.ean13 if x.ean_status == "valid" else None, "medicine_id": x.medicine_id,
                                        "is_current": x.medicine_id == med.id} for x in g.members]})
    pharmacological = []
    sig = _signature(med)
    if sig:
        ing_ids = [mi.ingredient_id for mi in med.ingredients]
        cands = db.scalars(select(m.Medicine).options(*_LOAD).join(m.MedicineIngredient)
                           .where(m.MedicineIngredient.ingredient_id.in_(ing_ids), m.Medicine.id != med.id)).unique()
        own_form = med.form.canonical if med.form else None
        for c in cands:
            if _signature(c) == sig:
                card = medicine_card(c)
                card["same_form"] = bool(own_form) and (c.form.canonical if c.form else None) == own_form
                pharmacological.append(card)
        pharmacological.sort(key=lambda c: (not c["same_form"], c["min_ppv"] if c["min_ppv"] is not None else 1e9))
    return {"medicine": medicine_card(med), "regulatory": regulatory, "pharmacological": pharmacological,
            "note": "Une même composition ne signifie pas automatiquement que les médicaments sont interchangeables : "
                    "seules les équivalences du Répertoire AMMPS sont réglementaires. Demandez à votre pharmacien."}
