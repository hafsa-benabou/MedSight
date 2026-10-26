from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models as m
from app.core.geo import haversine_km
from app.nlp.cities import canonical_city
from app.nlp.text import normalize_text
from app.services.catalog import STOCK_NOTICE, source_ref


def pharmacy_out(p: m.Pharmacy) -> dict:
    return {"id": p.id, "name": p.name, "address": p.address, "city": p.city, "district": p.district,
            "latitude": p.latitude, "longitude": p.longitude, "phone": p.phone, "opening_hours": p.opening_hours,
            "in_ammps_registry": p.in_ammps_registry, "data_status": p.data_status, "source": source_ref(p.source)}


def search_pharmacies(db: Session, *, city: str | None = None, q: str | None = None, lat: float | None = None,
                      lon: float | None = None, medicine_id: int | None = None, limit: int = 30) -> dict:
    stmt = select(m.Pharmacy).options(selectinload(m.Pharmacy.source))
    city_key, city_display = canonical_city(city) if city else (None, None)
    if city_key:
        stmt = stmt.where(m.Pharmacy.city_normalized == city_key)
    if q:
        stmt = stmt.where(m.Pharmacy.name_normalized.ilike(f"%{normalize_text(q)}%"))
    items = [pharmacy_out(p) for p in db.scalars(stmt.limit(2000))]
    if lat is not None and lon is not None:
        for it in items:
            it["distance_km"] = round(haversine_km(lat, lon, it["latitude"], it["longitude"]), 2) if it["latitude"] is not None else None
        items.sort(key=lambda it: (it["distance_km"] is None, it["distance_km"] or 0))
    else:
        items.sort(key=lambda it: (it["data_status"] != "official", it["name"]))
    items = items[:limit]
    if medicine_id:
        pres_ids = list(db.scalars(select(m.MedicinePresentation.id).where(m.MedicinePresentation.medicine_id == medicine_id)))
        rows = db.scalars(select(m.PharmacyInventory).where(m.PharmacyInventory.presentation_id.in_(pres_ids),
                                                            m.PharmacyInventory.pharmacy_id.in_([i["id"] for i in items]))).all()
        by_ph: dict[int, list] = {}
        for r in rows:
            by_ph.setdefault(r.pharmacy_id, []).append(r)
        for it in items:
            inv = by_ph.get(it["id"], [])
            verified = [r for r in inv if not r.is_simulated and r.data_status in ("official", "reference")]
            if verified:
                best = max(verified, key=lambda r: r.observed_at)
                it["availability"] = {"kind": "verified", "status": best.stock_status, "observed_at": best.observed_at.isoformat()}
            elif inv:
                it["availability"] = {"kind": "simulated", "status": inv[0].stock_status,
                                      "label": "SIMULATION — stock fictif de démonstration"}
            else:
                it["availability"] = {"kind": "unverified", "label": STOCK_NOTICE}
    return {"city": city_display, "items": items, "total": len(items), "stock_notice": STOCK_NOTICE}


def on_duty(db: Session, city: str | None = None, at: datetime | None = None) -> dict:
    at = at or datetime.now(timezone.utc)
    stmt = select(m.PharmacyDutyShift).options(selectinload(m.PharmacyDutyShift.source)).where(
        m.PharmacyDutyShift.starts_at <= at, m.PharmacyDutyShift.ends_at > at)
    city_key, city_display = canonical_city(city) if city else (None, None)
    if city_key:
        stmt = stmt.where(m.PharmacyDutyShift.city_normalized == city_key)
    items = [{"pharmacy_name": s.pharmacy_name, "city": s.city, "district": s.district, "address": s.address, "phone": s.phone,
              "shift_type": s.shift_type, "starts_at": s.starts_at.isoformat(), "ends_at": s.ends_at.isoformat(),
              "data_status": s.data_status, "source": source_ref(s.source), "source_url": s.source_url}
             for s in db.scalars(stmt)]
    return {"city": city_display, "at": at.isoformat(), "items": items}
