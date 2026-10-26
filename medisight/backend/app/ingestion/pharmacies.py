"""Pharmacies : registre AMMPS (nom + ville), OpenStreetMap (ODbL : adresse, GPS, téléphone, horaires),
listes de garde (import manuel sourcé). Aucune adresse, coordonnée ou stock n'est inventé."""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.core.geo import haversine_km
from app.ingestion.common import cell, import_run, read_rows, utcnow
from app.nlp.cities import canonical_city
from app.nlp.text import normalize_text

MA_TZ = ZoneInfo("Africa/Casablanca")
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_QUERY = """[out:json][timeout:300];
area["ISO3166-1"="MA"][admin_level=2]->.ma;
(node["amenity"="pharmacy"](area.ma); way["amenity"="pharmacy"](area.ma););
out center;
node["place"~"^(city|town)$"](area.ma);
out;"""


def pharmacy_name_key(name: str) -> str:
    return re.sub(r"^(pharmacie|pharmacy|صيدليه)\s+", "", normalize_text(name)).strip()


def _upsert(db: Session, ctx, key: str, **fields) -> None:
    obj = db.scalar(select(m.Pharmacy).where(m.Pharmacy.source_record_key == key))
    if obj is None:
        db.add(m.Pharmacy(source_record_key=key, source_id=ctx.source.id, **fields))
        ctx.run.rows_inserted += 1
    else:
        for k, v in fields.items():
            setattr(obj, k, v)
        ctx.run.rows_updated += 1


def import_ammps_pharmacies(db: Session, path: str | Path, *, version_date: date | None = None,
                            method: str = "file") -> dict:
    mapping, rows = read_rows(path, {"name": ["NOM DE LA PHARMACIE", "NOM", "PHARMACIE"], "city": ["VILLE"]},
                              min_matches=2)
    with import_run(db, "ammps_pharmacies", file_path=path, method=method, version_date=version_date) as ctx:
        for line, row in rows:
            ctx.run.rows_read += 1
            name, city = cell(row, mapping, "name"), cell(row, mapping, "city")
            if not name:
                ctx.reject("Nom de pharmacie manquant", line)
                continue
            city_key, city_display = canonical_city(city)
            _upsert(db, ctx, f"ammps:{normalize_text(name)}|{city_key}", name=str(name).strip(),
                    name_normalized=normalize_text(name), city=city_display, city_normalized=city_key,
                    in_ammps_registry=True, data_status="official")
        db.flush()
    return ctx.summary()


def fetch_osm(out_path: str | Path, url: str = OVERPASS_URL, timeout: float = 360.0) -> Path:
    """Télécharge les pharmacies OSM du Maroc (à exécuter sur une machine ayant accès à Internet)."""
    import httpx
    resp = httpx.post(url, data={"data": OVERPASS_QUERY}, timeout=timeout,
                      headers={"User-Agent": "MEDISIGHT-student-project/1.0 (INPT ChallengeCamp)"})
    resp.raise_for_status()
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(resp.text, encoding="utf-8")
    return out


def import_osm_json(db: Session, path: str | Path, *, version_date: date | None = None) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    elements = data.get("elements", [])
    places = [(e["lat"], e["lon"], e["tags"].get("name:fr") or e["tags"].get("name"))
              for e in elements if e.get("type") == "node" and e.get("tags", {}).get("place") in ("city", "town")
              and "lat" in e]
    registry: dict[str, list[str]] = {}
    for p in db.scalars(select(m.Pharmacy).where(m.Pharmacy.in_ammps_registry.is_(True),
                                                 m.Pharmacy.source_record_key.like("ammps:%"))):
        registry.setdefault(p.city_normalized or "", []).append(pharmacy_name_key(p.name))
    with import_run(db, "osm_pharmacies", file_path=path, version_date=version_date or utcnow().date()) as ctx:
        for e in elements:
            tags = e.get("tags", {})
            if tags.get("amenity") != "pharmacy":
                continue
            ctx.run.rows_read += 1
            lat = e.get("lat") or (e.get("center") or {}).get("lat")
            lon = e.get("lon") or (e.get("center") or {}).get("lon")
            if lat is None or lon is None:
                ctx.reject(f"Coordonnées absentes ({e.get('type')}/{e.get('id')})")
                continue
            name = tags.get("name:fr") or tags.get("name") or tags.get("name:ar") or "Pharmacie (nom non renseigné)"
            city_raw = tags.get("addr:city")
            if not city_raw and places:
                dist, nearest = min((haversine_km(lat, lon, p[0], p[1]), p[2]) for p in places)
                city_raw = nearest if dist <= 25 else None
            city_key, city_display = canonical_city(city_raw)
            address = " ".join(x for x in (tags.get("addr:housenumber"), tags.get("addr:street")) if x) or tags.get("addr:full")
            key = pharmacy_name_key(name)
            in_registry = any(fuzz.token_set_ratio(key, r) >= 92 for r in registry.get(city_key or "", [])) if key else None
            _upsert(db, ctx, f"osm:{e['type']}/{e['id']}", name=name, name_normalized=normalize_text(name),
                    address=address, city=city_display, city_normalized=city_key,
                    district=tags.get("addr:suburb") or tags.get("addr:district"),
                    latitude=float(lat), longitude=float(lon),
                    phone=tags.get("phone") or tags.get("contact:phone"), opening_hours=tags.get("opening_hours"),
                    in_ammps_registry=in_registry, data_status="unverified")
        db.flush()
    return ctx.summary()


def _parse_local(raw) -> datetime | None:
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=MA_TZ)
    if not raw:
        return None
    s = str(raw).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%d/%m/%Y %H:%M"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=MA_TZ)
        except ValueError:
            continue
    return None


DUTY_COLUMNS = {"name": ["PHARMACY NAME", "PHARMACIE", "NOM"], "city": ["CITY", "VILLE"], "district": ["DISTRICT", "QUARTIER"],
                "address": ["ADDRESS", "ADRESSE"], "phone": ["PHONE", "TELEPHONE", "TÉLÉPHONE"],
                "type": ["SHIFT TYPE", "GARDE TYPE", "TYPE"], "start": ["STARTS AT", "DEBUT", "START DATETIME"],
                "end": ["ENDS AT", "FIN", "END DATETIME"], "url": ["SOURCE URL", "SOURCE"],
                "status": ["DATA STATUS", "STATUT"]}


def import_duty_shifts(db: Session, path: str | Path, *, source_code: str = "duty_manual") -> dict:
    mapping, rows = read_rows(path, DUTY_COLUMNS, min_matches=4)
    with import_run(db, source_code, file_path=path) as ctx:
        for line, row in rows:
            ctx.run.rows_read += 1
            name, city = cell(row, mapping, "name"), cell(row, mapping, "city")
            start, end = _parse_local(cell(row, mapping, "start")), _parse_local(cell(row, mapping, "end"))
            shift = normalize_text(cell(row, mapping, "type") or "")
            shift = {"jour": "jour", "nuit": "nuit", "24h": "24h", "24 h": "24h", "24/24": "24h"}.get(shift)
            status = cell(row, mapping, "status") or ctx.source.default_data_status
            if not (name and city and start and end and shift) or end <= start or status not in m.DATA_STATUSES:
                ctx.reject("Ligne de garde incomplète ou incohérente (nom, ville, type, début < fin, statut)", line)
                continue
            city_key, city_display = canonical_city(city)
            target = pharmacy_name_key(name)
            pharmacy = next((p for p in db.scalars(select(m.Pharmacy).where(m.Pharmacy.city_normalized == city_key))
                             if fuzz.token_set_ratio(pharmacy_name_key(p.name), target) >= 92), None)
            db.add(m.PharmacyDutyShift(pharmacy_id=pharmacy.id if pharmacy else None, pharmacy_name=str(name),
                                       city=city_display, city_normalized=city_key, district=cell(row, mapping, "district"),
                                       address=cell(row, mapping, "address"), phone=cell(row, mapping, "phone"),
                                       shift_type=shift, starts_at=start, ends_at=end, source_id=ctx.source.id,
                                       source_url=cell(row, mapping, "url"), data_status=status))
            ctx.run.rows_inserted += 1
        db.flush()
    return ctx.summary()
