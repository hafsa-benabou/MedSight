"""Import des variantes de noms commerciaux (écriture arabe, graphie lue sur l'emballage, variantes OCR).

Chaque variante doit citer sa référence (photo d'emballage, notice, RCP) ; elle n'est rattachée qu'à une spécialité
existante identifiée par nom + dosage + forme (jamais créée), puis ajoutée au texte de recherche."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.ingestion.common import cell, import_run, medicine_key, read_rows, refresh_search_text
from app.nlp.text import has_arabic, normalize_text

ALIAS_COLUMNS = {
    "brand": ["SPECIALITE", "SPÉCIALITÉ"], "dosage": ["DOSAGE"], "form": ["FORME"], "alias": ["ALIAS", "VARIANTE"],
    "language": ["LANGUE", "LANGUAGE"], "kind": ["TYPE", "KIND"], "reference": ["SOURCE REFERENCE", "REFERENCE"],
}
KINDS = {"brand_variant", "arabic_script", "packaging_text", "ocr_variant"}


def import_aliases_file(db: Session, path: str | Path, *, source_code: str = "manual_aliases") -> dict:
    mapping, rows = read_rows(path, ALIAS_COLUMNS, min_matches=4)
    with import_run(db, source_code, file_path=path, method="manual_transcription") as ctx:
        for line, row in rows:
            ctx.run.rows_read += 1
            brand, alias, ref = cell(row, mapping, "brand"), cell(row, mapping, "alias"), cell(row, mapping, "reference")
            if not brand or not alias or not ref:
                ctx.reject("Spécialité, variante et référence sont obligatoires", line)
                continue
            key = medicine_key(str(brand), cell(row, mapping, "dosage"), cell(row, mapping, "form"))
            med = db.scalar(select(m.Medicine).where(m.Medicine.source_record_key == key))
            if med is None:
                ctx.reject(f"Spécialité introuvable : {key}", line)
                continue
            kind = (cell(row, mapping, "kind") or ("arabic_script" if has_arabic(str(alias)) else "brand_variant")).lower()
            if kind not in KINDS:
                ctx.reject(f"Type de variante inconnu : {kind}", line)
                continue
            norm = normalize_text(alias)
            obj = db.scalar(select(m.MedicineAlias).where(m.MedicineAlias.medicine_id == med.id,
                                                          m.MedicineAlias.alias_normalized == norm))
            if obj is None:
                obj = m.MedicineAlias(medicine_id=med.id, alias=str(alias).strip(), alias_normalized=norm,
                                      source_id=ctx.source.id, data_status=ctx.source.default_data_status, kind=kind)
                db.add(obj)
                ctx.run.rows_inserted += 1
            else:
                ctx.run.rows_updated += 1
            obj.kind, obj.language, obj.source_reference = kind, cell(row, mapping, "language"), str(ref)[:500]
            db.flush()
            db.refresh(med, ["aliases"])
            refresh_search_text(med)
    return ctx.summary()
