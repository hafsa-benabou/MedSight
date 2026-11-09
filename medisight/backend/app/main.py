"""API REST MEDISIGHT (documentation interactive : /docs)."""
from __future__ import annotations

import logging
import time

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app import models as m
from app.core.config import get_settings
from app.core.errors import AppError, error_body
from app.core.logging import setup_logging
from app.core.ratelimit import RateLimiter
from app.db.session import get_db
from app.services import catalog, chat, pharmacies
from app.vision.barcodes import available_readers
from app.vision.identify import identify_image
from app.vision.ocr import OcrEngine, default_engine

settings = get_settings()
setup_logging(settings.log_level)
log = logging.getLogger("medisight.api")
limiter = RateLimiter()
app = FastAPI(title=settings.app_name, version=settings.app_version,
              description="API d'information pharmaceutique (Maroc). Information, pas un avis médical.")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST", "DELETE"],
                   allow_headers=["*"])


@app.middleware("http")
async def guard(request: Request, call_next):
    start = time.perf_counter()
    if settings.rate_limit_enabled and request.url.path.startswith("/api/"):
        limit = settings.rate_limit_chat if "/chat" in request.url.path else (
            settings.rate_limit_pills if "/pills" in request.url.path else settings.rate_limit_default)
        ip = request.client.host if request.client else "unknown"
        ok, retry = limiter.hit(f"{ip}:{request.url.path.split('/')[2]}", limit, settings.rate_limit_window_seconds)
        if not ok:
            return JSONResponse(error_body("rate_limited", "Trop de requêtes, réessayez plus tard."), status_code=429,
                                headers={"Retry-After": str(retry)})
    response = await call_next(request)
    response.headers.update({"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer"})
    log.info("%s %s -> %s (%.0f ms)", request.method, request.url.path, response.status_code, (time.perf_counter() - start) * 1000)
    return response


@app.exception_handler(AppError)
async def app_error(_: Request, exc: AppError):
    return JSONResponse(error_body(exc.code, exc.message, exc.details), status_code=exc.status_code)


@app.exception_handler(OperationalError)
async def db_down(_: Request, exc: OperationalError):
    log.error("Base de données indisponible : %s", str(exc).splitlines()[0][:200])
    return JSONResponse(error_body("database_unavailable", "Base de données temporairement indisponible."), status_code=503)


@app.get("/api/health", tags=["système"])
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    counts = {k: v for k, v in db.execute(select(m.Medicine.data_status, func.count()).group_by(m.Medicine.data_status),
                                          execution_options={"include_simulated": True})}
    return {"status": "ok", "version": settings.app_version, "database": "ok", "medicines_by_status": counts,
            "simulated_data_exposed": settings.show_simulated_data,
            "modules": {"catalog": "ready", "pharmacies": "ready", "chatbot": {"engine": "rules+sql", "llm": "none"},
                        "pill_identifier": {"ocr": default_engine().status(), "barcode_readers": available_readers()}}}


@app.get("/api/sources", tags=["système"])
def sources(db: Session = Depends(get_db)):
    out = []
    stmt = select(m.DataSource).order_by(m.DataSource.is_official.desc(), m.DataSource.name)
    if not settings.show_simulated_data:
        stmt = stmt.where(m.DataSource.default_data_status != "simulated")
    for s in db.scalars(stmt):
        last = db.scalar(select(m.DataImport).where(m.DataImport.source_id == s.id, m.DataImport.status.in_(["success", "partial"]))
                         .order_by(m.DataImport.finished_at.desc()).limit(1))
        out.append({"code": s.code, "name": s.name, "publisher": s.publisher, "url": s.url, "license": s.license,
                    "is_official": s.is_official, "default_data_status": s.default_data_status, "market": s.market,
                    "reuse_conditions": s.reuse_conditions, "notes": s.notes,
                    "last_import": None if last is None else {
                        "finished_at": last.finished_at.isoformat() if last.finished_at else None, "method": last.method,
                        "version_date": last.source_version_date.isoformat() if last.source_version_date else None,
                        "rows": last.rows_read}})
    return out


@app.get("/api/medicines", tags=["médicaments"])
@app.get("/api/medicines/search", tags=["médicaments"])
def medicines_search(q: str = Query("", max_length=120), form: str | None = Query(None, max_length=40),
                     status: str | None = Query(None, pattern="^(official|reference|unverified|simulated)$"),
                     page: int = Query(1, ge=1, le=500), size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    return catalog.search_medicines(db, q, form=form, status=status, page=page, size=size)


@app.get("/api/medicines/autocomplete", tags=["médicaments"])
def medicines_autocomplete(q: str = Query(..., min_length=2, max_length=80), db: Session = Depends(get_db)):
    return catalog.autocomplete(db, q)


@app.get("/api/medicines/{medicine_id}", tags=["médicaments"])
def medicine_detail(medicine_id: int, db: Session = Depends(get_db)):
    data = catalog.medicine_detail(db, medicine_id)
    if data is None:
        raise HTTPException(404, "Médicament introuvable")
    return data


@app.get("/api/medicines/{medicine_id}/generics", tags=["médicaments"])
def medicine_generics(medicine_id: int, db: Session = Depends(get_db)):
    data = catalog.generics_for(db, medicine_id)
    if data is None:
        raise HTTPException(404, "Médicament introuvable")
    return data


@app.get("/api/pharmacies", tags=["pharmacies"])
@app.get("/api/pharmacies/search", tags=["pharmacies"])
def pharmacies_search(city: str | None = Query(None, max_length=80), q: str | None = Query(None, max_length=80),
                      lat: float | None = Query(None, ge=20, le=37), lon: float | None = Query(None, ge=-18, le=0),
                      medicine_id: int | None = None, limit: int = Query(30, ge=1, le=100), db: Session = Depends(get_db)):
    return pharmacies.search_pharmacies(db, city=city, q=q, lat=lat, lon=lon, medicine_id=medicine_id, limit=limit)


@app.get("/api/pharmacies/on-duty", tags=["pharmacies"])
def pharmacies_on_duty(city: str | None = Query(None, max_length=80), db: Session = Depends(get_db)):
    return pharmacies.on_duty(db, city)


def get_ocr_engine() -> OcrEngine:
    return default_engine()


@app.post("/api/pills/identify", tags=["pill identifier"])
def pills_identify(file: UploadFile = File(..., description="Photo de la boîte (JPEG, PNG ou WEBP)"),
                   db: Session = Depends(get_db), engine: OcrEngine = Depends(get_ocr_engine)):
    """Analyse une photo de boîte : code-barres, OCR, extraction, rapprochement avec le catalogue marocain.
    L'image n'est pas conservée (STORE_UPLOADED_IMAGES=false) et ne quitte pas le serveur."""
    max_bytes = int(settings.max_upload_mb * 1024 * 1024)
    data = file.file.read(max_bytes + 1)  # lecture bornée : un fichier énorme n'est jamais chargé en entier
    return identify_image(db, data, settings, engine)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    conversation_id: str | None = Field(None, max_length=64)
    context_medicine_id: int | None = Field(None, ge=1, description="Identifiant PostgreSQL du médicament (ex. issu du Pill Identifier)")


@app.post("/api/chat", tags=["chatbot"])
def chat_message(body: ChatRequest, db: Session = Depends(get_db)):
    """Assistant pharmaceutique (français, arabe, darija) : réponse construite à partir de la base, sources citées.
    Le texte saisi n'est pas conservé ; seule son analyse l'est pendant CONVERSATION_RETENTION_HOURS."""
    return chat.handle_message(db, settings, body.message.strip() or "?", conversation_id=body.conversation_id,
                               context_medicine_id=body.context_medicine_id)


@app.get("/api/chat/suggestions", tags=["chatbot"])
def chat_suggestions(medicine_id: int | None = Query(None, ge=1), lang: str = Query("fr", pattern="^(fr|ar)$"),
                     db: Session = Depends(get_db)):
    med = None
    if medicine_id is not None:
        med = db.get(m.Medicine, medicine_id)
        if med is None:
            raise HTTPException(404, "Médicament introuvable")
    return {"medicine": catalog.medicine_card(catalog_load(db, med.id)) if med else None,
            "suggestions": chat.suggestions_for(med, lang)}


def catalog_load(db: Session, medicine_id: int) -> m.Medicine:
    return db.scalar(select(m.Medicine).options(*catalog._LOAD).where(m.Medicine.id == medicine_id))


@app.delete("/api/chat/{conversation_id}", tags=["chatbot"])
def chat_delete(conversation_id: str, db: Session = Depends(get_db)):
    """Efface immédiatement une conversation et son analyse (droit à l'effacement)."""
    import uuid
    try:
        conv = db.get(m.Conversation, uuid.UUID(conversation_id))
    except ValueError:
        raise HTTPException(404, "Conversation introuvable") from None
    if conv is None:
        raise HTTPException(404, "Conversation introuvable")
    db.delete(conv)
    db.commit()
    return {"deleted": True}
