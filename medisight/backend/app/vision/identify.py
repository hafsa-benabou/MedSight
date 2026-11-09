"""Orchestration du Pill Identifier : image -> validation -> qualité -> code-barres -> OCR -> extraction -> matching.

Statuts renvoyés : identified, ambiguous, contradictory, not_found, unreadable, ocr_unavailable.
Confidentialité : l'image n'est ni stockée (sauf STORE_UPLOADED_IMAGES=true) ni transmise à un service externe ;
la trace en base (identification_results) contient l'empreinte SHA-256, les entités extraites et les candidats,
jamais l'image ni le texte OCR brut (une boîte peut porter une étiquette nominative de pharmacie)."""
from __future__ import annotations

import time
from datetime import timedelta

from sqlalchemy.orm import Session

from app import models as m
from app.core.config import Settings
from app.ingestion.common import utcnow
from app.vision.barcodes import read_barcodes
from app.vision.extraction import extract
from app.vision.images import load_image, store_upload
from app.vision.matching import candidate_out, load_vocabulary, match
from app.vision.ocr import OcrEngine, OcrResult, OcrUnavailable, group_lines
from app.vision.preprocess import assess_quality, rotate, to_gray, variants

GOOD_OCR_SCORE = 25.0  # caractères lus avec confiance : au-delà, inutile d'essayer d'autres variantes
MIN_USEFUL_SCORE = 6.0
MIN_WORD_CONFIDENCE = 35.0
DISCLAIMER = ("Résultat indicatif fondé sur une photo : faites toujours confirmer le médicament par un pharmacien. "
              "En cas d'urgence : SAMU 141, Protection civile 15.")
MESSAGES = {
    "identified": "Correspondance étayée par plusieurs indices concordants.",
    "ambiguous": "Plusieurs médicaments possibles : vérifiez le nom et le dosage sur la boîte.",
    "contradictory": "Les indices se contredisent : identification impossible sans vérification.",
    "not_found": "Aucun médicament du catalogue ne correspond aux informations lues.",
    "unreadable": "Photo inexploitable : reprenez-la nette, bien éclairée, la face portant le nom bien visible.",
    "ocr_unavailable": "Lecture du texte indisponible sur le serveur et aucun code-barres lu.",
}


def verdict(status: str, level: str | None, reliability: str, top: dict | None) -> str:
    """Lecture prudente du résultat, fondée sur la nature des indices et non sur l'indice numérique :
    - confirmed : une présentation précise, étayée par des indices indépendants (code-barres corroboré, ou nom +
      dosage + forme/conditionnement/substance), sans contradiction ni laboratoire divergent ;
    - partial : médicament candidat reconnu mais présentation non confirmée, ou plusieurs candidats possibles ;
    - failed : contradiction déterminante, aucune correspondance, photo ou OCR inexploitable."""
    if status == "identified":
        lab_differs = bool(top and top["evidence"].get("laboratory") == "conflict")
        if level == "presentation" and reliability == "high" and not lab_differs:
            return "confirmed"
        return "partial"
    return "partial" if status == "ambiguous" else "failed"


def run_ocr(engine: OcrEngine, bgr, max_passes: int) -> tuple[OcrResult | None, list[dict]]:
    """Essaie les variantes de prétraitement puis, si rien n'est lisible, les rotations ; garde la meilleure lecture."""
    best: OcrResult | None = None
    trials: list[dict] = []
    for name, img in variants(bgr):
        if len(trials) >= max_passes:
            break
        res = engine.read(img)
        res.variant = name
        trials.append({"variant": name, "rotation": 0, "score": round(res.score, 1),
                       "mean_confidence": round(res.mean_confidence, 1), "ms": round(res.elapsed_ms)})
        if best is None or res.score > best.score:
            best = res
        if best.score >= GOOD_OCR_SCORE and best.mean_confidence >= 70:
            break
    if best is not None and best.score < MIN_USEFUL_SCORE:
        gray = to_gray(bgr)
        for angle in (90, 270, 180):  # boîte photographiée de côté ou à l'envers
            if len(trials) >= max_passes:
                break
            res = engine.read(rotate(gray, angle))
            res.variant, res.rotation = "gray", angle
            trials.append({"variant": "gray", "rotation": angle, "score": round(res.score, 1),
                           "mean_confidence": round(res.mean_confidence, 1), "ms": round(res.elapsed_ms)})
            if res.score > best.score:
                best = res
    return best, trials


def identify_image(db: Session, data: bytes, settings: Settings, engine: OcrEngine, *, persist: bool = True) -> dict:
    t0 = time.perf_counter()
    timings: dict[str, float] = {}
    image = load_image(data, settings)  # AppError 413 / 415 / 422 si le fichier est refusé
    timings["decode_ms"] = (time.perf_counter() - t0) * 1000
    warnings: list[str] = []

    t = time.perf_counter()
    quality = assess_quality(image.bgr, settings.min_image_side)
    barcodes = read_barcodes(image.bgr)
    timings["quality_barcode_ms"] = (time.perf_counter() - t) * 1000

    ocr_status = engine.status()
    ocr_best: OcrResult | None = None
    trials: list[dict] = []
    ocr_error = None
    t = time.perf_counter()
    if ocr_status.get("available"):
        # photo jugée inutilisable : un seul passage, au cas où les seuils (heuristiques) seraient trop sévères
        try:
            ocr_best, trials = run_ocr(engine, image.bgr, settings.ocr_max_passes if quality.usable else 1)
        except OcrUnavailable as exc:
            ocr_error = str(exc)
    else:
        ocr_error = ocr_status.get("reason", "OCR indisponible")
    timings["ocr_ms"] = (time.perf_counter() - t) * 1000
    if ocr_error:
        warnings.append(f"OCR indisponible : {ocr_error}")
    if ocr_best:
        warnings.extend(ocr_best.warnings)

    words = [w for w in (ocr_best.words if ocr_best else []) if w.confidence >= MIN_WORD_CONFIDENCE]
    lines = group_lines(words)
    t = time.perf_counter()
    extracted = extract([(line.text, line.height) for line in lines], load_vocabulary(db))
    result = match(db, extracted, barcodes, include_simulated=settings.pill_include_simulated)
    timings["match_ms"] = (time.perf_counter() - t) * 1000
    warnings.extend(result.warnings)
    if settings.pill_include_simulated:
        warnings.append("Mode démonstration : des données simulées peuvent figurer parmi les candidats")

    status, reasons = result.status, list(result.reasons)
    readable_text = bool(ocr_best and ocr_best.score >= MIN_USEFUL_SCORE)
    if status != "identified" and not barcodes:
        if ocr_error:
            status = "ocr_unavailable"
        elif not readable_text and (not quality.usable or not extracted.has_evidence):
            status = "unreadable"
            reasons.append("Qualité : " + (", ".join(quality.issues) or "aucun texte lisible"))
    if not quality.usable and status not in ("unreadable",):
        warnings.append("Qualité de photo insuffisante (" + ", ".join(quality.issues) + ") : résultat à vérifier")

    candidates = [candidate_out(c, i + 1) for i, c in enumerate(result.candidates)]
    reliability = result.reliability if status in ("identified", "ambiguous", "contradictory") else "none"
    level = result.level if status == "identified" else None
    assessment = verdict(status, level, reliability, candidates[0] if candidates else None)
    message = MESSAGES[status]
    if status == "identified" and assessment != "confirmed":
        top = candidates[0]
        message = (f"{top['brand']} {top['dosage'] or ''}".strip()
                   + " reconnu comme médicament candidat — présentation exacte non confirmée.")
    now = utcnow()
    trace = m.IdentificationResult(
        expires_at=now + timedelta(hours=settings.identification_retention_hours), image_sha256=image.sha256,
        image_stored=False, hints={"quality": quality.summary(), "ocr_trials": trials},
        extracted={**extracted.summary(), "barcodes": [b.summary() for b in barcodes]},
        candidates=[{k: c[k] for k in ("rank", "score", "medicine_id", "presentation_id", "evidence")} for c in candidates],
        best_score=candidates[0]["score"] if candidates else None, reliability=reliability)
    if persist:
        stored = store_upload(image, settings)
        trace.image_stored = stored is not None
        db.add(trace)
        db.commit()
    timings["total_ms"] = (time.perf_counter() - t0) * 1000

    return {
        "identification_id": str(trace.id) if persist else None, "status": status, "message": message,
        "verdict": assessment, "reliability": reliability, "identified_level": level,
        "score_note": "Indice heuristique de correspondance (0-100) : ni une probabilité ni une précision mesurée.",
        "reasons": reasons, "warnings": list(dict.fromkeys(warnings)),
        "barcodes": [{**b.summary(), "in_catalog": result.barcode_catalog.get(b.code or "", False)} for b in barcodes],
        "extracted": extracted.summary(),
        "candidates": candidates,
        "presentation_ids": [c["presentation_id"] for c in candidates] if status == "identified" else [],
        "available_dosages": result.available_dosages,
        "ocr": {"engine": ocr_status.get("engine"), "available": bool(ocr_status.get("available")) and not ocr_error,
                "languages": ocr_status.get("languages"), "version": ocr_status.get("version"),
                "variant": ocr_best.variant if ocr_best else None, "rotation": ocr_best.rotation if ocr_best else 0,
                "mean_confidence": round(ocr_best.mean_confidence, 1) if ocr_best else None,
                "passes": trials,
                "lines": [{"text": line.text, "confidence": round(line.confidence, 1), "bbox": line.bbox}
                          for line in lines]},
        "image": {**image.summary(), "stored": trace.image_stored},
        "quality": quality.summary(),
        "timings_ms": {k: round(v) for k, v in timings.items()},
        "disclaimer": DISCLAIMER,
    }
