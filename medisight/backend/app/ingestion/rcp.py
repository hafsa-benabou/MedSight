"""Extraction des rubriques d'un RCP (4.1 à 4.9) ou d'une notice patient, à partir d'un PDF ou d'un texte.
Le texte est conservé tel quel avec sa source : aucune reformulation clinique."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.ingestion.common import import_run
from app.nlp.text import normalize_text

SECTION_RULES = [
    ("composition", r"^2\.?\s+composition"), ("form", r"^3\.?\s+forme pharmaceutique"),
    ("indications", r"^4\.1\.?\s+indications"), ("posology", r"^4\.2\.?\s+posologie"),
    ("contraindications", r"^4\.3\.?\s+contre.?indications"), ("warnings", r"^4\.4\.?\s+mises en garde"),
    ("interactions", r"^4\.5\.?\s+interactions"), ("pregnancy", r"^4\.6\.?\s+(fertilite|grossesse)"),
    ("driving", r"^4\.7\.?\s+effets sur l.?aptitude"), ("side_effects", r"^4\.8\.?\s+effets indesirables"),
    ("overdose", r"^4\.9\.?\s+surdosage"),
    ("indications", r"^1\.?\s+qu est.?ce que .* (dans quels? cas|utilise)"),
    ("contraindications", r"^2\.?\s+quelles sont les informations a connaitre"),
    ("posology", r"^3\.?\s+comment (prendre|utiliser)"), ("side_effects", r"^4\.?\s+quels sont les effets indesirables"),
]
SECTION_TITLES = {
    "composition": "Composition", "form": "Forme pharmaceutique", "indications": "Indications thérapeutiques",
    "posology": "Posologie et mode d'administration", "contraindications": "Contre-indications",
    "warnings": "Mises en garde et précautions d'emploi", "interactions": "Interactions médicamenteuses",
    "pregnancy": "Grossesse et allaitement", "driving": "Conduite de véhicules", "side_effects": "Effets indésirables",
    "overdose": "Surdosage",
}
_BOUNDARY = re.compile(r"^(\d{1,2}\.\d{1,2}\.?\s+\S|\d{1,2}\.?\s+[A-ZÉÈÀÂÎÔÛ][A-ZÉÈÀÂÎÔÛ'\s,-]{4,}$)")


def extract_text(path: str | Path) -> str:
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    return path.read_text(encoding="utf-8", errors="replace")


def split_sections(text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current, buf = None, []

    def flush():
        if current and "\n".join(buf).strip():
            sections.setdefault(current, "\n".join(buf).strip())

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        norm = normalize_text(line)
        code = next((c for c, pat in SECTION_RULES if re.match(pat, norm)), None)
        if code or (len(line) < 120 and _BOUNDARY.match(line)):
            flush()
            current, buf = code, []
            continue
        if current:
            buf.append(line)
    flush()
    return sections


def import_rcp_file(db: Session, path: str | Path, *, medicine_id: int, source_url: str | None = None,
                    document_date: date | None = None, from_ammps: bool = False) -> dict:
    med = db.get(m.Medicine, medicine_id)
    if med is None:
        raise ValueError(f"Médicament {medicine_id} introuvable")
    sections = split_sections(extract_text(path))
    if not sections:
        raise ValueError("Aucune rubrique RCP/notice reconnue dans le document")
    with import_run(db, "rcp_documents", file_path=path, version_date=document_date) as ctx:
        status = "official" if from_ammps else "unverified"
        for code, content in sections.items():
            ctx.run.rows_read += 1
            row = db.scalar(select(m.ClinicalSection).where(m.ClinicalSection.medicine_id == med.id,
                                                            m.ClinicalSection.section_code == code,
                                                            m.ClinicalSection.source_id == ctx.source.id))
            if row is None:
                row = m.ClinicalSection(medicine_id=med.id, section_code=code, source_id=ctx.source.id)
                db.add(row)
                ctx.run.rows_inserted += 1
            else:
                ctx.run.rows_updated += 1
            row.title, row.content = SECTION_TITLES.get(code, code), content
            row.source_url = source_url or med.rcp_url
            row.document_date = document_date
            row.extraction_method = "rcp_pdf_parser" if str(path).lower().endswith(".pdf") else "rcp_text_parser"
            row.data_status = status
        db.flush()
    return {**ctx.summary(), "sections": sorted(sections)}
