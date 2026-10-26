"""Import d'interactions documentées (DDInter 2.0 ou saisie manuelle sourcée, ex. Thésaurus ANSM).
Les substances inconnues sont rejetées (jamais créées) ; aucune interaction n'est déduite ni inventée."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.ingestion.common import cell, import_run, read_rows
from app.nlp.text import normalize_text

SEVERITY = {
    "contraindicated": "contraindicated", "contre indication": "contraindicated", "contre-indication": "contraindicated",
    "major": "major", "majeure": "major", "association deconseillee": "major",
    "moderate": "moderate", "moderee": "moderate", "precaution d emploi": "moderate",
    "minor": "minor", "mineure": "minor", "a prendre en compte": "minor", "unknown": "unknown", "inconnue": "unknown",
}
COLUMNS = {"a": ["DRUG A", "DRUG_A", "INGREDIENT A", "INGREDIENT_A", "SUBSTANCE A"],
           "b": ["DRUG B", "DRUG_B", "INGREDIENT B", "INGREDIENT_B", "SUBSTANCE B"],
           "level": ["LEVEL", "SEVERITY", "NIVEAU", "GRAVITE"], "description": ["DESCRIPTION", "MECANISME"],
           "management": ["MANAGEMENT", "CONDUITE A TENIR", "RECOMMANDATION"], "reference": ["SOURCE REFERENCE", "REFERENCE"]}


def ingredient_resolver(db: Session):
    lookup: dict[str, int] = {}
    for ing in db.scalars(select(m.ActiveIngredient)):
        for name in [ing.name, ing.inn_en, *(ing.synonyms or [])]:
            if name:
                lookup.setdefault(normalize_text(name), ing.id)
    return lambda raw: lookup.get(normalize_text(raw or ""))


def import_interactions_file(db: Session, path: str | Path, *, source_code: str = "manual_interactions") -> dict:
    mapping, rows = read_rows(path, COLUMNS, min_matches=3)
    resolve = ingredient_resolver(db)
    with import_run(db, source_code, file_path=path) as ctx:
        unknown: dict[str, int] = {}
        for line, row in rows:
            ctx.run.rows_read += 1
            raw_a, raw_b = cell(row, mapping, "a"), cell(row, mapping, "b")
            ia, ib = resolve(raw_a), resolve(raw_b)
            if not ia or not ib or ia == ib:
                for raw, found in ((raw_a, ia), (raw_b, ib)):
                    if not found and raw:
                        unknown[str(raw)] = unknown.get(str(raw), 0) + 1
                ctx.reject("Substance non reconnue dans le référentiel", line)
                continue
            level_raw = str(cell(row, mapping, "level") or "unknown")
            severity = SEVERITY.get(normalize_text(level_raw), "unknown")
            a, b = sorted((ia, ib))
            obj = db.scalar(select(m.DrugInteraction).where(m.DrugInteraction.ingredient_a_id == a,
                                                            m.DrugInteraction.ingredient_b_id == b,
                                                            m.DrugInteraction.source_id == ctx.source.id))
            if obj is None:
                obj = m.DrugInteraction(ingredient_a_id=a, ingredient_b_id=b, source_id=ctx.source.id)
                db.add(obj)
                ctx.run.rows_inserted += 1
            else:
                ctx.run.rows_updated += 1
            obj.severity, obj.severity_raw = severity, level_raw
            obj.description, obj.management = cell(row, mapping, "description"), cell(row, mapping, "management")
            obj.source_reference = cell(row, mapping, "reference")
            obj.data_status = ctx.source.default_data_status
        db.flush()
        if unknown:
            ctx.warn(f"Substances non reconnues (top 20) : {sorted(unknown, key=unknown.get, reverse=True)[:20]}")
    return ctx.summary()
