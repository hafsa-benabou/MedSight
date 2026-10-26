"""Jeu initial : référentiel de substances, échantillons officiels transcrits (statut official),
démonstration simulée (statut simulated, purgeable). Idempotent."""
from __future__ import annotations

import csv
import hashlib
from datetime import date, datetime, time, timedelta
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import models as m
from app.core.config import get_settings
from app.ingestion.common import cell, get_source, import_run, read_rows, utcnow
from app.ingestion.generics import import_generics_file
from app.ingestion.medicines import import_medicines_file
from app.ingestion.pharmacies import MA_TZ, import_ammps_pharmacies
from app.nlp.cities import canonical_city
from app.nlp.text import normalize_text

SAMPLES = {
    "medicines": "samples/ammps_medicaments_page1.csv",
    "generics": "samples/ammps_generiques_projet_2026-01_extrait.csv",
    "pharmacies": "samples/ammps_pharmacies_page1.csv",
}
DEMO = {"medicines": "demo/demo_medicines_SIMULATED.csv", "pharmacies": "demo/demo_pharmacies_SIMULATED.csv"}


def load_reference_ingredients(db: Session, path: Path) -> int:
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln and not ln.startswith("#")]
    count = 0
    for row in csv.DictReader(lines, delimiter=";"):
        key = normalize_text(row["name"])
        ing = db.scalar(select(m.ActiveIngredient).where(m.ActiveIngredient.name_normalized == key))
        if ing is None:
            ing = m.ActiveIngredient(name=row["name"].strip().upper(), name_normalized=key)
            db.add(ing)
        ing.inn_en = row.get("inn_en") or None
        ing.name_ar = row.get("name_ar") or None
        ing.synonyms = [s.strip() for s in (row.get("synonyms") or "").split("|") if s.strip()]
        count += 1
    db.commit()
    return count


def seed_demo_pharmacies(db: Session, path: Path) -> dict:
    mapping, rows = read_rows(path, {"name": ["NOM"], "city": ["VILLE"], "address": ["ADRESSE"],
                                     "lat": ["LATITUDE"], "lon": ["LONGITUDE"]}, min_matches=3)
    with import_run(db, "demo_simulated", file_path=path, method="seed") as ctx:
        for _, row in rows:
            ctx.run.rows_read += 1
            name = cell(row, mapping, "name")
            city_key, city_display = canonical_city(cell(row, mapping, "city"))
            key = f"demo:{normalize_text(name)}"
            ph = db.scalar(select(m.Pharmacy).where(m.Pharmacy.source_record_key == key))
            if ph is None:
                ph = m.Pharmacy(source_record_key=key, source_id=ctx.source.id)
                db.add(ph)
                ctx.run.rows_inserted += 1
            else:
                ctx.run.rows_updated += 1
            ph.name, ph.name_normalized, ph.city, ph.city_normalized = name, normalize_text(name), city_display, city_key
            ph.address, ph.data_status, ph.in_ammps_registry = cell(row, mapping, "address"), "simulated", None
            ph.latitude, ph.longitude = float(cell(row, mapping, "lat")), float(cell(row, mapping, "lon"))
        db.flush()
    return ctx.summary()


def seed_simulated_inventory_and_duty(db: Session) -> dict:
    src = get_source(db, "demo_simulated")
    db.execute(delete(m.PharmacyInventory).where(m.PharmacyInventory.is_simulated.is_(True)))
    db.execute(delete(m.PharmacyDutyShift).where(m.PharmacyDutyShift.data_status == "simulated"))
    pharmacies = list(db.scalars(select(m.Pharmacy).where(m.Pharmacy.data_status == "simulated")))
    presentations = list(db.scalars(select(m.MedicinePresentation).where(m.MedicinePresentation.data_status == "simulated")))
    now, statuses, n_inv = utcnow(), ("in_stock", "in_stock", "low", "out_of_stock"), 0
    for ph in pharmacies:
        for pres in presentations:
            h = int(hashlib.sha256(f"{ph.id}-{pres.id}".encode()).hexdigest(), 16)
            db.add(m.PharmacyInventory(pharmacy_id=ph.id, presentation_id=pres.id, stock_status=statuses[h % 4],
                                       quantity=None, observed_at=now, is_simulated=True, source_id=src.id,
                                       data_status="simulated"))
            n_inv += 1
    today = datetime.now(MA_TZ).date()
    n_duty = 0
    for ph in pharmacies:
        if ph.city_normalized in ("casablanca", "rabat") and ("maarif" in ph.name_normalized or "agdal" in ph.name_normalized):
            for day in (today - timedelta(days=1), today):
                start = datetime.combine(day, time(20, 0), MA_TZ)
                db.add(m.PharmacyDutyShift(pharmacy_id=ph.id, pharmacy_name=ph.name, city=ph.city,
                                           city_normalized=ph.city_normalized, address=ph.address, shift_type="nuit",
                                           starts_at=start, ends_at=start + timedelta(hours=13), source_id=src.id,
                                           data_status="simulated"))
                n_duty += 1
    db.commit()
    return {"source": "demo_simulated", "inventory_rows": n_inv, "duty_shifts": n_duty}


def seed_all(db: Session, data_dir: Path | None = None, include_simulated: bool = True) -> list[dict]:
    data_dir = Path(data_dir or get_settings().data_dir)
    reports: list[dict] = [{"reference_ingredients": load_reference_ingredients(db, data_dir / "reference/ingredient_synonyms.csv")}]
    reports.append(import_medicines_file(db, data_dir / SAMPLES["medicines"], source_code="ammps_medicaments",
                                         version_date=date(2026, 10, 1), method="manual_transcription"))
    reports.append(import_generics_file(db, data_dir / SAMPLES["generics"], edition="Édition projet – janvier 2026",
                                        version_date=date(2026, 1, 12), method="manual_transcription"))
    reports.append(import_ammps_pharmacies(db, data_dir / SAMPLES["pharmacies"], version_date=date(2026, 10, 25),
                                           method="manual_transcription"))
    if include_simulated:
        reports.append(import_medicines_file(db, data_dir / DEMO["medicines"], source_code="demo_simulated",
                                             data_status="simulated", method="seed"))
        reports.append(seed_demo_pharmacies(db, data_dir / DEMO["pharmacies"]))
        reports.append(seed_simulated_inventory_and_duty(db))
    return reports


def purge_simulated(db: Session) -> dict:
    counts = {}
    for model in (m.PharmacyInventory, m.PharmacyDutyShift, m.Pharmacy, m.MedicinePresentation, m.Medicine,
                  m.ClinicalSection, m.DrugInteraction, m.MedicineImage):
        counts[model.__tablename__] = db.execute(delete(model).where(model.data_status == "simulated")).rowcount
    db.commit()
    return counts


def purge_expired(db: Session) -> dict:
    now = utcnow()
    out = {"conversations": db.execute(delete(m.Conversation).where(m.Conversation.expires_at < now)).rowcount,
           "identifications": db.execute(delete(m.IdentificationResult).where(m.IdentificationResult.expires_at < now)).rowcount}
    db.commit()
    return out
