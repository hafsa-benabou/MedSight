"""Import de la base des médicaments au format AMMPS (export CSV/XLSX ou saisie manuelle)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from app import models as m
from app.ingestion.common import (RefCache, cell, import_run, norm_princeps, parse_price, read_rows,
                                  split_substances, upsert_medicine, upsert_presentation)

AMMPS_COLUMNS = {
    "brand": ["SPECIALITE", "SPÉCIALITÉ", "NOM", "NOM COMMERCIAL", "DESIGNATION", "DÉNOMINATION"],
    "dosage": ["DOSAGE"],
    "form": ["FORME", "FORME PHARMACEUTIQUE", "FORME GALENIQUE"],
    "presentation": ["PRESENTATION", "PRÉSENTATION", "CONDITIONNEMENT"],
    "princeps": ["PP GN", "PP/GN", "PRINCEPS/GENERIQUE", "PRINCEPS GENERIQUE", "TYPE", "P/G"],
    "substances": ["SUBSTANCE ACTIVE", "SUBSTANCES ACTIVES", "DCI", "PRINCIPE ACTIF"],
    "therapeutic_class": ["CLASSE THERAPEUTIQUE", "CLASSE THÉRAPEUTIQUE"],
    "laboratory": ["EPI", "LABORATOIRE", "TITULAIRE"],
    "ppv": ["PPV", "PRIX PUBLIC", "PRIX PUBLIC DE VENTE"],
    "ph": ["PH", "PRIX HOPITAL", "PRIX HÔPITAL", "PRIX HOSPITALIER"],
    "pfht": ["PFHT"],
    "amm_status": ["STATUT AMM"],
    "marketing_status": ["STATUT COMMERCIALISATION", "STATUT DE COMMERCIALISATION"],
    "ean": ["EAN", "EAN13", "EAN 13", "CODE EAN", "CODE BARRE"],
    "atc": ["ATC", "CODE ATC"],
    "rcp_url": ["RCP", "RCP URL", "LIEN RCP"],
    "source_url": ["URL", "URL FICHE", "LIEN FICHE", "REFERENCE FICHE", "SOURCE URL"],
}


def import_medicines_file(db: Session, path: str | Path, *, source_code: str = "ammps_medicaments",
                          version_date: date | None = None, data_status: str | None = None,
                          method: str = "file") -> dict:
    mapping, rows = read_rows(path, AMMPS_COLUMNS, min_matches=3)
    if "brand" not in mapping:
        raise ValueError("Colonne SPECIALITE/NOM introuvable")
    with import_run(db, source_code, file_path=path, method=method, version_date=version_date) as ctx:
        cache = RefCache(db)
        for line, row in rows:
            ctx.run.rows_read += 1
            brand = cell(row, mapping, "brand")
            if not brand:
                ctx.reject("Nom commercial manquant", line)
                continue
            substances = split_substances(cell(row, mapping, "substances"))
            if not substances:
                ctx.warn(f"Substance active manquante pour {brand}", line)
            med, created = upsert_medicine(
                ctx, cache, brand=str(brand), dosage=cell(row, mapping, "dosage"), form_label=cell(row, mapping, "form"),
                substances=substances, laboratory=cell(row, mapping, "laboratory"),
                therapeutic_class=cell(row, mapping, "therapeutic_class"),
                princeps=norm_princeps(cell(row, mapping, "princeps")), amm_status=cell(row, mapping, "amm_status"),
                marketing_status=cell(row, mapping, "marketing_status"), rcp_url=cell(row, mapping, "rcp_url"),
                atc=cell(row, mapping, "atc"), source_url=cell(row, mapping, "source_url"), data_status=data_status)
            status = data_status or ctx.source.default_data_status
            if m.STATUS_RANK[status] < m.STATUS_RANK[med.data_status]:
                # fiche plus fiable déjà présente : aucune présentation ni aucun prix moins fiable n'y est rattaché
                ctx.warn(f"{brand} {med.dosage_text or ''} : fiche {med.data_status} existante, ligne {status} ignorée", line)
                ctx.run.rows_rejected += 1
                continue
            ppv, ppv_status = parse_price(cell(row, mapping, "ppv"))
            ph, _ = parse_price(cell(row, mapping, "ph"))
            pfht, _ = parse_price(cell(row, mapping, "pfht"))
            _, p_created = upsert_presentation(
                ctx, med, label=cell(row, mapping, "presentation"), ppv=ppv, ph=ph, pfht=pfht,
                price_status=ppv_status if "ppv" in mapping else "unknown", price_as_of=version_date,
                ean=cell(row, mapping, "ean"), data_status=data_status)
            if created or p_created:
                ctx.run.rows_inserted += 1
            else:
                ctx.run.rows_updated += 1
    return ctx.summary()
