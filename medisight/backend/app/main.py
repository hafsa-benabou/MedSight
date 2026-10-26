"""API REST MEDISIGHT (documentation interactive : /docs)."""
from __future__ import annotations

import logging
import time

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app import models as m
from app.core.config import get_settings
from app.core.errors import AppError, error_body
from app.core.logging import setup_logging
from app.core.ratelimit import RateLimiter
from app.db.session import get_db
from app.services import catalog, pharmacies

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
    counts = {k: v for k, v in db.execute(select(m.Medicine.data_status, func.count()).group_by(m.Medicine.data_status))}
    return {"status": "ok", "version": settings.app_version, "database": "ok", "medicines_by_status": counts,
            "modules": {"catalog": "ready", "pharmacies": "ready", "chatbot": "lot 2", "pill_identifier": "lot 3"}}


@app.get("/api/sources", tags=["système"])
def sources(db: Session = Depends(get_db)):
    out = []
    for s in db.scalars(select(m.DataSource).order_by(m.DataSource.is_official.desc(), m.DataSource.name)):
        last = db.scalar(select(m.DataImport).where(m.DataImport.source_id == s.id, m.DataImport.status.in_(["success", "partial"]))
                         .order_by(m.DataImport.finished_at.desc()).limit(1))
        out.append({"code": s.code, "name": s.name, "publisher": s.publisher, "url": s.url, "license": s.license,
                    "is_official": s.is_official, "default_data_status": s.default_data_status, "notes": s.notes,
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
