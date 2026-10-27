"""Corpus de photos de référence (boîtes marocaines présentes dans le catalogue) et évaluation du Pill Identifier.

- import_corpus : lit un manifeste CSV (modèle data/templates/pill_corpus_TEMPLATE.csv), rattache chaque photo à
  une présentation EXISTANTE (par EAN-13, sinon par nom + dosage + forme + présentation), enregistre ses
  métadonnées (face, langues, origine, licence, qualité mesurée) dans medicine_images et la transcription
  humaine dans image_annotations. Idempotent (empreinte SHA-256 unique). Les fichiers restent dans data/corpus/.
- evaluate : passe chaque photo dans le pipeline réel (sans trace en base) et mesure ce qui a été réellement obtenu."""
from __future__ import annotations

import statistics
import time
from datetime import datetime
from pathlib import Path

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.core.config import Settings
from app.core.ean import normalize_ean
from app.ingestion.common import cell, file_sha256, import_run, medicine_key, read_rows
from app.nlp.text import normalize_text
from app.vision.identify import identify_image
from app.vision.images import load_image
from app.vision.ocr import OcrEngine
from app.vision.preprocess import assess_quality

CORPUS_COLUMNS = {
    "file": ["IMAGE FILE", "FICHIER"], "brand": ["SPECIALITE"], "dosage": ["DOSAGE"], "form": ["FORME"],
    "presentation": ["PRESENTATION"], "ean": ["EAN13", "EAN 13"], "view": ["VIEW", "FACE"],
    "languages": ["LANGUAGES", "LANGUES"], "origin": ["ORIGIN", "ORIGINE"], "license": ["LICENSE", "LICENCE"],
    "attribution": ["ATTRIBUTION", "AUTEUR"], "captured_at": ["CAPTURED AT", "DATE PRISE DE VUE"],
    "transcription": ["TRANSCRIPTION"], "notes": ["NOTES"],
}
VIEWS = {"front", "back", "side", "top", "bottom", "inside", "other"}
ORIGINS = {"team_photo", "manufacturer", "public_dataset", "user_consented"}


def _presentation(db: Session, row, mapping) -> m.MedicinePresentation | None:
    code, status = normalize_ean(cell(row, mapping, "ean"))
    if code and status == "valid":
        pres = db.scalar(select(m.MedicinePresentation).where(m.MedicinePresentation.ean13 == code))
        if pres is not None:
            return pres
    key = medicine_key(str(cell(row, mapping, "brand") or ""), cell(row, mapping, "dosage"), cell(row, mapping, "form"))
    med = db.scalar(select(m.Medicine).where(m.Medicine.source_record_key == key))
    label = normalize_text(cell(row, mapping, "presentation") or "")
    if med is None:
        return None
    return next((p for p in med.presentations if p.label_normalized == label), None)


def import_corpus(db: Session, manifest: str | Path, settings: Settings) -> dict:
    manifest = Path(manifest)
    mapping, rows = read_rows(manifest, CORPUS_COLUMNS, min_matches=5)
    with import_run(db, "pill_corpus", file_path=manifest, method="manual_transcription") as ctx:
        for line, row in rows:
            ctx.run.rows_read += 1
            rel = cell(row, mapping, "file")
            path = (manifest.parent / str(rel)).resolve() if rel else None
            if not path or not path.exists():
                ctx.reject(f"Photo introuvable : {rel}", line)
                continue
            lic, origin = cell(row, mapping, "license"), (cell(row, mapping, "origin") or "").lower()
            view = (cell(row, mapping, "view") or "").lower() or None
            if not lic:
                ctx.reject("Licence obligatoire (photo d'équipe : préciser par ex. « CC BY 4.0 — équipe »)", line)
                continue
            if origin not in ORIGINS or (view and view not in VIEWS):
                ctx.reject(f"Origine ({origin}) ou face ({view}) non reconnue", line)
                continue
            pres = _presentation(db, row, mapping)
            if pres is None:
                ctx.reject("Présentation introuvable dans le catalogue : la photo n'est jamais rattachée au hasard", line)
                continue
            if pres.data_status == "simulated":
                ctx.reject("Présentation simulée : une photo réelle n'est pas rattachée à une fiche fictive", line)
                continue
            digest = file_sha256(path)
            img = db.scalar(select(m.MedicineImage).where(m.MedicineImage.sha256 == digest))
            if img is None:
                img = m.MedicineImage(sha256=digest, kind="box", source_id=ctx.source.id, data_status="unverified",
                                      is_moroccan_reference=True)
                db.add(img)
                ctx.run.rows_inserted += 1
            else:
                ctx.run.rows_updated += 1
            loaded = load_image(path.read_bytes(), settings)
            quality = assess_quality(loaded.bgr, settings.min_image_side)
            captured = cell(row, mapping, "captured_at")
            img.medicine_id, img.presentation_id = pres.medicine_id, pres.id
            img.file_path = str(path.relative_to(Path(settings.data_dir).resolve())) \
                if Path(settings.data_dir).resolve() in path.parents else str(path)
            img.license, img.attribution, img.origin, img.view = str(lic), cell(row, mapping, "attribution"), origin, view
            img.packaging_languages = [x.strip() for x in str(cell(row, mapping, "languages") or "").split("|") if x.strip()]
            img.width_px, img.height_px = loaded.original_size
            img.captured_at = datetime.fromisoformat(str(captured)) if captured else None
            img.metadata_json = {"quality": quality.summary(), "notes": cell(row, mapping, "notes")}
            db.flush()
            text = cell(row, mapping, "transcription")
            if text:
                ann = next((a for a in img.annotations if a.annotation_type == "ocr_text" and a.annotator == "human"), None)
                if ann is None:
                    ann = m.ImageAnnotation(image_id=img.id, annotation_type="ocr_text", annotator="human")
                    db.add(ann)
                ann.value = str(text).replace(" | ", "\n")
                ann.language = (img.packaging_languages or [None])[0]
                ann.is_verified = True
            db.flush()
    return ctx.summary()


def evaluate(db: Session, settings: Settings, engine: OcrEngine) -> dict:
    """Mesures réelles sur les photos du corpus rattachées à une présentation (aucune trace d'identification)."""
    images = list(db.scalars(select(m.MedicineImage).where(m.MedicineImage.presentation_id.is_not(None))))
    rows, statuses = [], {}
    for img in images:
        path = Path(img.file_path)
        path = path if path.is_absolute() else Path(settings.data_dir) / path
        if not path.exists():
            rows.append({"image_id": img.id, "error": "fichier absent"})
            continue
        t = time.perf_counter()
        r = identify_image(db, path.read_bytes(), settings, engine, persist=False)
        elapsed = (time.perf_counter() - t) * 1000
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1
        pres = db.get(m.MedicinePresentation, img.presentation_id)
        human = next((a.value for a in img.annotations if a.annotation_type == "ocr_text" and a.annotator == "human"), None)
        ocr_text = " ".join(line["text"] for line in r["ocr"]["lines"])
        rows.append({
            "image_id": img.id, "expected_presentation_id": pres.id, "status": r["status"],
            "top1_presentation": bool(r["candidates"]) and r["candidates"][0]["presentation_id"] == pres.id,
            "top3_medicine": any(c["medicine_id"] == pres.medicine_id for c in r["candidates"][:3]),
            "identified_correctly": r["status"] == "identified" and pres.id in r["presentation_ids"],
            "identified_wrongly": r["status"] == "identified" and pres.id not in r["presentation_ids"],
            "barcode_expected": bool(pres.ean13) and img.view in ("back", "side", "bottom", None),
            "barcode_read": any(b["code"] == pres.ean13 for b in r["barcodes"]) if pres.ean13 else None,
            "ocr_similarity": round(fuzz.ratio(normalize_text(human), normalize_text(ocr_text)), 1) if human else None,
            "ms": round(elapsed)})
    done = [x for x in rows if "error" not in x]

    def rate(key):
        vals = [x[key] for x in done if x[key] is not None]
        return round(sum(vals) / len(vals), 3) if vals else None

    sims = [x["ocr_similarity"] for x in done if x["ocr_similarity"] is not None]
    return {"images": len(images), "evaluated": len(done), "statuses": statuses,
            "identified_correctly_rate": rate("identified_correctly"), "identified_wrongly_rate": rate("identified_wrongly"),
            "top1_presentation_rate": rate("top1_presentation"), "top3_medicine_rate": rate("top3_medicine"),
            "barcode_read_rate": rate("barcode_read"),
            "ocr_similarity_mean": round(statistics.mean(sims), 1) if sims else None,
            "latency_ms_median": statistics.median([x["ms"] for x in done]) if done else None,
            "note": "Mesures sur le corpus local uniquement ; à interpréter avec la taille de l'échantillon.",
            "rows": rows}
