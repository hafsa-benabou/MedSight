"""CLI du pipeline de données : python -m app.ingestion.cli <commande> [options]."""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from sqlalchemy import func, select

from app import models as m
from app.core.config import get_settings
from app.db.session import session_scope


def _date(value: str) -> date:
    return date.fromisoformat(value)


def stats(db) -> dict:
    out = {}
    for model in (m.Medicine, m.MedicinePresentation, m.GenericGroup, m.Reimbursement, m.ClinicalSection,
                  m.DrugInteraction, m.Pharmacy, m.PharmacyDutyShift, m.PharmacyInventory):
        if hasattr(model, "data_status"):
            rows = db.execute(select(model.data_status, func.count()).group_by(model.data_status)).all()
            out[model.__tablename__] = {k: v for k, v in rows}
        else:
            out[model.__tablename__] = db.scalar(select(func.count()).select_from(model))
    out["active_ingredients"] = db.scalar(select(func.count()).select_from(m.ActiveIngredient))
    out["generic_group_members"] = db.scalar(select(func.count()).select_from(m.GenericGroupMember))
    out["last_imports"] = [
        {"source": r.source.code, "status": r.status, "method": r.method, "file": r.file_name,
         "version": str(r.source_version_date) if r.source_version_date else None, "finished": str(r.finished_at)}
        for r in db.scalars(select(m.DataImport).order_by(m.DataImport.id.desc()).limit(10))]
    return out


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="medisight-data", description="Pipeline de données MEDISIGHT")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed", help="Référentiel + échantillons officiels + démo simulée").add_argument("--no-simulated", action="store_true")
    s = sub.add_parser("import-ammps", help="Export AMMPS (CSV/XLSX)"); s.add_argument("file"); s.add_argument("--version-date", type=_date)
    s = sub.add_parser("import-generics", help="Répertoire des génériques (CSV/XLSX)"); s.add_argument("file")
    s.add_argument("--edition"); s.add_argument("--version-date", type=_date)
    s = sub.add_parser("import-cnops", help="Référentiel CNOPS data.gov.ma (XLSX)"); s.add_argument("file")
    s.add_argument("--sheet"); s.add_argument("--version-date", type=_date, default=date(2014, 1, 1)); s.add_argument("--dry-run", action="store_true")
    s = sub.add_parser("import-ammps-pharmacies"); s.add_argument("file")
    s = sub.add_parser("fetch-osm", help="Télécharge les pharmacies OSM (Internet requis)"); s.add_argument("--out")
    s = sub.add_parser("import-osm"); s.add_argument("file")
    s = sub.add_parser("import-duty", help="Pharmacies de garde (CSV modèle)"); s.add_argument("file")
    s = sub.add_parser("import-rcp", help="Rubriques RCP/notice d'un médicament"); s.add_argument("file")
    s.add_argument("--medicine-id", type=int, required=True); s.add_argument("--source-url")
    s.add_argument("--document-date", type=_date); s.add_argument("--from-ammps", action="store_true")
    s = sub.add_parser("import-interactions"); s.add_argument("file")
    s.add_argument("--source", choices=["ddinter", "manual_interactions"], default="manual_interactions")
    for name in ("purge-simulated", "purge-expired", "stats"):
        sub.add_parser(name)
    a = p.parse_args(argv)

    with session_scope() as db:
        if a.cmd == "seed":
            from app.ingestion.seed import seed_all
            result = seed_all(db, include_simulated=not a.no_simulated)
        elif a.cmd == "import-ammps":
            from app.ingestion.medicines import import_medicines_file
            result = import_medicines_file(db, a.file, version_date=a.version_date)
        elif a.cmd == "import-generics":
            from app.ingestion.generics import import_generics_file
            result = import_generics_file(db, a.file, edition=a.edition, version_date=a.version_date)
        elif a.cmd == "import-cnops":
            from app.ingestion.cnops import import_cnops_file
            result = import_cnops_file(db, a.file, version_date=a.version_date, sheet=a.sheet, dry_run=a.dry_run)
        elif a.cmd == "import-ammps-pharmacies":
            from app.ingestion.pharmacies import import_ammps_pharmacies
            result = import_ammps_pharmacies(db, a.file)
        elif a.cmd == "fetch-osm":
            from app.ingestion.pharmacies import fetch_osm
            out = a.out or str(get_settings().data_dir / "raw" / f"osm_pharmacies_{date.today()}.json")
            result = {"saved": str(fetch_osm(out))}
        elif a.cmd == "import-osm":
            from app.ingestion.pharmacies import import_osm_json
            result = import_osm_json(db, a.file)
        elif a.cmd == "import-duty":
            from app.ingestion.pharmacies import import_duty_shifts
            result = import_duty_shifts(db, a.file)
        elif a.cmd == "import-rcp":
            from app.ingestion.rcp import import_rcp_file
            result = import_rcp_file(db, a.file, medicine_id=a.medicine_id, source_url=a.source_url,
                                     document_date=a.document_date, from_ammps=a.from_ammps)
        elif a.cmd == "import-interactions":
            from app.ingestion.interactions import import_interactions_file
            result = import_interactions_file(db, a.file, source_code=a.source)
        elif a.cmd == "purge-simulated":
            from app.ingestion.seed import purge_simulated
            result = purge_simulated(db)
        elif a.cmd == "purge-expired":
            from app.ingestion.seed import purge_expired
            result = purge_expired(db)
        else:
            result = stats(db)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
