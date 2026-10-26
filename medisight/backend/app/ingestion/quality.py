"""Contrôle qualité de la base (étape finale du pipeline) : python -m app.ingestion.cli quality [--strict].

Deux niveaux :
- critical : violation d'une règle de fiabilité (donnée simulée rattachée à une fiche réelle, EAN invalide stocké,
  prix sans date, prix historique présenté comme courant, source étrangère dans le catalogue marocain…) ;
- warning : anomalie à examiner (doublons probables, dosages non structurés, membres du répertoire non rattachés…).
Chaque contrôle renvoie un compteur et quelques exemples pour faciliter la correction."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased, selectinload

from app import models as m
from app.core.ean import ean13_is_valid

HISTORICAL_PRICE_SOURCES = ("cnops_referentiel",)
STALE_PRICE_DAYS = 730


def _check(code: str, severity: str, description: str, samples: list) -> dict:
    return {"code": code, "severity": severity, "description": description, "count": len(samples), "samples": samples[:10]}


def _label(med: m.Medicine) -> str:
    return f"#{med.id} {med.brand_name} {med.dosage_text or ''}".strip()


def run_quality_checks(db: Session, *, today: date | None = None) -> dict:
    today = today or date.today()
    checks: list[dict] = []
    P, M, S = m.MedicinePresentation, m.Medicine, m.DataSource

    rows = db.execute(select(P.id, M.brand_name, P.label).select_from(P).join(M).where(P.data_status == "simulated",
                                                                       M.data_status != "simulated")).all()
    checks.append(_check("simulated_presentation_on_real_medicine", "critical",
                         "Présentation simulée rattachée à une fiche non simulée", [f"#{i} {b} {l}" for i, b, l in rows]))

    rows = db.execute(select(P.id, P.ean13).where(P.ean13.is_not(None))).all()
    checks.append(_check("invalid_ean_stored", "critical", "EAN-13 stocké avec une clé de contrôle invalide",
                         [f"#{i} {e}" for i, e in rows if not ean13_is_valid(e)]))

    dup = db.execute(select(P.ean13, func.count(func.distinct(P.medicine_id))).where(P.ean13.is_not(None))
                     .group_by(P.ean13).having(func.count(func.distinct(P.medicine_id)) > 1)).all()
    checks.append(_check("duplicate_ean_across_medicines", "critical", "Même EAN-13 sur plusieurs spécialités",
                         [f"{e} ({n} fiches)" for e, n in dup]))

    samples = []
    for model in (M, P, m.GenericGroup, m.Reimbursement, m.ClinicalSection, m.Pharmacy):
        for i, code in db.execute(select(model.id, S.code).select_from(model).join(S, model.source_id == S.id)
                                  .where(model.data_status == "official", S.is_official.is_(False))):
            samples.append(f"{model.__tablename__}#{i} ({code})")
    checks.append(_check("official_status_from_non_official_source", "critical",
                         "Statut official attribué à une donnée issue d'une source non officielle", samples))

    rows = db.execute(select(P.id, M.brand_name, P.label).select_from(P).join(M).where(P.price_status == "priced",
                                                                       P.price_as_of.is_(None),
                                                                       P.data_status != "simulated")).all()
    checks.append(_check("price_without_date", "critical", "Prix réel sans date de validité",
                         [f"#{i} {b} {l}" for i, b, l in rows]))

    rows = db.execute(select(P.id, M.brand_name, S.code).select_from(P).join(M).join(S, P.source_id == S.id)
                      .where(P.price_status == "priced", S.code.in_(HISTORICAL_PRICE_SOURCES))).all()
    checks.append(_check("historical_price_as_current", "critical",
                         "Prix d'une source historique (CNOPS 2014) stocké comme prix courant",
                         [f"#{i} {b} ({c})" for i, b, c in rows]))

    rows = db.execute(select(M.id, M.brand_name, S.code, S.market).select_from(M).join(S, M.source_id == S.id)
                      .where(S.market.is_not(None), S.market != "MA")).all()
    checks.append(_check("foreign_market_in_catalog", "critical", "Spécialité issue d'un marché autre que le Maroc",
                         [f"#{i} {b} ({c}, {mk})" for i, b, c, mk in rows]))

    # ---------- avertissements ----------
    meds = list(db.scalars(select(M).options(selectinload(M.ingredients), selectinload(M.form),
                                             selectinload(M.presentations))))
    groups: dict[tuple, list[m.Medicine]] = defaultdict(list)
    for med in meds:
        sig = tuple(sorted((mi.ingredient_id, str(mi.strength_mg) if mi.strength_mg is not None else (mi.strength_text or ""))
                           for mi in med.ingredients))
        if sig:
            groups[(med.brand_normalized, med.form.canonical if med.form else None, sig)].append(med)
    checks.append(_check("duplicate_medicine_candidates", "warning",
                         "Même nom, même forme canonique et même composition dosée sous plusieurs fiches "
                         "(ex. « 0,5 G » et « 500 MG ») : à fusionner après vérification",
                         [" = ".join(_label(x) for x in g) for g in groups.values() if len(g) > 1]))

    checks.append(_check("medicine_without_ingredient", "warning", "Spécialité sans substance active",
                         [_label(x) for x in meds if not x.ingredients]))
    checks.append(_check("medicine_without_presentation", "warning", "Spécialité sans présentation",
                         [_label(x) for x in meds if not x.presentations]))
    checks.append(_check("unstructured_strength", "warning",
                         "Plusieurs substances mais dosage non réparti par substance (comparaisons impossibles)",
                         [_label(x) for x in meds if len(x.ingredients) > 1 and x.dosage_text
                          and any(mi.strength_text is None for mi in x.ingredients)]))

    rows = db.execute(select(m.GenericGroupMember.raw_label, m.GenericGroupMember.match_method)
                      .where(m.GenericGroupMember.medicine_id.is_(None))).all()
    checks.append(_check("generic_member_unlinked", "warning",
                         "Membre du répertoire non rattaché (dosage/forme incohérents avec le groupe, ou dosage absent)",
                         [f"{r} ({mm})" for r, mm in rows]))

    gm = aliased(m.GenericGroupMember)
    rows = db.execute(select(M.id, M.brand_name, M.dosage_text).select_from(M).join(S, M.source_id == S.id)
                      .outerjoin(gm, gm.medicine_id == M.id).where(S.code == "ammps_generiques", gm.id.is_(None))).all()
    checks.append(_check("repertoire_medicine_orphan", "warning",
                         "Fiche créée depuis le répertoire mais plus rattachée à aucun membre (ancienne analyse du libellé)",
                         [f"#{i} {b} {d or ''}".strip() for i, b, d in rows]))

    rows = db.execute(select(P.id, M.brand_name, P.ppv_mad, P.ph_mad).select_from(P).join(M)
                      .where(P.ppv_mad.is_not(None))).all()
    checks.append(_check("price_anomaly", "warning", "PPV nul ou négatif, ou PH supérieur au PPV",
                         [f"#{i} {b} PPV {ppv} PH {ph}" for i, b, ppv, ph in rows
                          if ppv <= 0 or (ph is not None and ph > ppv)]))

    limit = today - timedelta(days=STALE_PRICE_DAYS)
    rows = db.execute(select(P.id, M.brand_name, P.price_as_of).select_from(P).join(M)
                      .where(P.price_status == "priced", P.data_status != "simulated", P.price_as_of < limit)).all()
    checks.append(_check("stale_price", "warning", f"Prix daté de plus de {STALE_PRICE_DAYS} jours",
                         [f"#{i} {b} ({d})" for i, b, d in rows]))

    rows = db.execute(select(m.MedicineImage.id).where(m.MedicineImage.presentation_id.is_(None))).all()
    checks.append(_check("image_without_presentation", "warning",
                         "Photo non rattachée à une présentation (inutilisable comme référence du Pill Identifier)",
                         [f"image#{i}" for (i,) in rows]))

    critical = sum(c["count"] for c in checks if c["severity"] == "critical")
    warnings = sum(c["count"] for c in checks if c["severity"] == "warning")
    return {"date": today.isoformat(), "critical": critical, "warnings": warnings, "checks": checks}
