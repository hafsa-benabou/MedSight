"""Import du référentiel CNOPS (data.gov.ma, ODbL) : prix 2014 et bases de remboursement.

Les prix CNOPS sont historiques : ils sont conservés dans `reimbursements` (ppv_reference_mad, ph_reference_mad,
valid_as_of) et ne sont jamais recopiés comme prix courant d'une présentation. Ils ne peuvent donc ni écraser un prix
AMMPS, ni être affichés comme un prix actuel. Seul le code EAN (s'il est valide) enrichit la présentation."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import models as m
from app.ingestion.common import (RefCache, cell, import_run, medicine_key, norm_princeps, parse_percent, parse_price,
                                  read_rows, split_substances, upsert_medicine, upsert_presentation)

CNOPS_COLUMNS = {
    "brand": ["NOM", "SPECIALITE", "DESIGNATION", "NOM COMMERCIAL", "LIBELLE"],
    "substances": ["DCI", "DCI1", "DCI 1", "SUBSTANCE ACTIVE"],
    "dosage": ["DOSAGE", "DOSAGE1", "DOSAGE 1"],
    "unit": ["UNITE", "UNITE1", "UNITE DOSAGE", "UNITE DOSAGE1", "UNITE_DOSAGE1", "UNITE_DOSAGE"],
    "form": ["FORME", "FORME PHARMACEUTIQUE"],
    "presentation": ["PRESENTATION", "PRÉSENTATION", "CONDITIONNEMENT"],
    "ppv": ["PPV", "PRIX PUBLIC", "PRIX PPV", "PRIX PUBLIC DE VENTE"],
    "ph": ["PH", "PRIX HOPITAL", "PRIX HOSPITALIER"],
    "base": ["PRIX BR", "PRIX_BR", "BASE DE REMBOURSEMENT", "BASE REMBOURSEMENT", "BR", "PRIX DE REFERENCE"],
    "type": ["PRINCEPS GENERIQUE", "PRINCEPS_GENERIQUE", "P/G", "TYPE", "PRINCEPS/GENERIQUE"],
    "rate": ["TAUX REMBOURSEMENT", "TAUX_REMBOURSEMENT", "TAUX", "TAUX DE REMBOURSEMENT"],
    "code": ["CODE", "CODE EAN", "EAN", "CODE_EAN"],
}


def import_cnops_file(db: Session, path: str | Path, *, version_date: date = date(2014, 1, 1), sheet: str | None = None,
                      dry_run: bool = False) -> dict:
    mapping, rows = read_rows(path, CNOPS_COLUMNS, min_matches=4, sheet=sheet)
    if dry_run:
        return {"mapping": mapping, "rows": len(rows), "sample": [r for _, r in rows[:5]]}
    with import_run(db, "cnops_referentiel", file_path=path, version_date=version_date) as ctx:
        # idempotence : on remplace uniquement les lignes de la même version du référentiel
        db.execute(delete(m.Reimbursement).where(m.Reimbursement.source_id == ctx.source.id,
                                                 m.Reimbursement.valid_as_of == version_date))
        cache = RefCache(db)
        for line, row in rows:
            ctx.run.rows_read += 1
            brand = cell(row, mapping, "brand")
            if not brand:
                ctx.reject("Nom manquant", line)
                continue
            dosage = cell(row, mapping, "dosage")
            unit = cell(row, mapping, "unit")
            dosage_text = f"{dosage} {unit}".strip() if dosage is not None and unit else (str(dosage) if dosage is not None else None)
            form = cell(row, mapping, "form")
            key = medicine_key(str(brand), dosage_text, form)
            med = db.scalar(select(m.Medicine).where(m.Medicine.source_record_key == key))
            method = "exact"
            if med is None:
                med, _ = upsert_medicine(ctx, cache, brand=str(brand), dosage=dosage_text, form_label=form,
                                         substances=split_substances(cell(row, mapping, "substances")),
                                         princeps=norm_princeps(cell(row, mapping, "type")))
                method = "created"
            ppv, ppv_status = parse_price(cell(row, mapping, "ppv"))
            ph, _ = parse_price(cell(row, mapping, "ph"))
            if ppv_status == "unknown" and cell(row, mapping, "ppv") is not None:
                ctx.warn(f"Prix illisible pour {brand} : {cell(row, mapping, 'ppv')!r}", line)
            pres, created = upsert_presentation(ctx, med, label=cell(row, mapping, "presentation"),
                                                ean=cell(row, mapping, "code"))
            base, _ = parse_price(cell(row, mapping, "base"))
            db.add(m.Reimbursement(medicine_id=med.id, presentation_id=pres.id, raw_name=str(brand),
                                   raw_presentation=cell(row, mapping, "presentation"), base_remboursement_mad=base,
                                   taux_remboursement=parse_percent(cell(row, mapping, "rate")),
                                   princeps_generique=str(cell(row, mapping, "type") or "")[:32] or None,
                                   ppv_reference_mad=ppv, ph_reference_mad=ph, valid_as_of=version_date,
                                   match_method=method, data_status="official", source_id=ctx.source.id))
            if created or method == "created":
                ctx.run.rows_inserted += 1
            else:
                ctx.run.rows_updated += 1
    return ctx.summary()
