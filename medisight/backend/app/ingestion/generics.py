"""Import du Répertoire Marocain des Médicaments Génériques (AMMPS) : groupes, type P/G, EAN-13."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.core.ean import normalize_ean
from app.ingestion.common import (RefCache, cell, import_run, medicine_key, read_rows, split_substances,
                                  upsert_medicine, upsert_presentation)
from app.nlp.text import normalize_text

GENERIC_COLUMNS = {
    "group": ["GROUPE", "GROUPE GENERIQUE", "GROUPE GÉNÉRIQUE"],
    "route": ["VOIE", "VOIE D'ADMINISTRATION", "VOIE D ADMINISTRATION"],
    "type": ["TYPE"],
    "specialty": ["SPECIALITE", "SPÉCIALITÉ", "SPECIALITE PHARMACEUTIQUE", "SPÉCIALITÉ PHARMACEUTIQUE"],
    "laboratory": ["EPI", "LABORATOIRE"],
    "ean": ["EAN", "EAN13", "EAN 13"],
}
_UNIT_WORDS = {"mg", "g", "ml", "l", "ui", "u", "mui", "mmol", "meq", "mbq", "gbq", "uceip", "µg", "mcg", "ug", "dose", "doses", "%", "/"}
_PRESENTATION_RE = re.compile(r"\b(BOITE|BOÎTE|OITE|FLACON|TUBE|ETUI|ÉTUI|PLAQUETTE|POT|AMPOULES?|SACHETS?|SERINGUES?|STYLOS?)\b")


def _is_dosage_token(token: str) -> bool:
    return bool(re.match(r"^[\d.,/%]+", token)) or token.lower() in _UNIT_WORDS


def _split_dosage(tokens: list[str]) -> tuple[str | None, list[str]]:
    j = 0
    while j < len(tokens) and _is_dosage_token(tokens[j]):
        j += 1
    return (" ".join(tokens[:j]) or None), tokens[j:]


def parse_group_label(label: str) -> tuple[list[str], str | None, str | None]:
    """« AMLODIPINE 5 MG COMPRIME » -> (["AMLODIPINE"], "5 MG", "COMPRIME")."""
    tokens = label.split()
    first = next((i for i, t in enumerate(tokens) if re.match(r"^\[?\d", t)), None)
    if first is None:
        return split_substances(label), None, None
    dosage, rest = _split_dosage(tokens[first:])
    return split_substances(" ".join(tokens[:first])), dosage, " ".join(rest) or None


def parse_member_label(label: str) -> tuple[str, str | None, str | None, str | None]:
    """« AMLOR 5 MG COMPRIME BOITE DE 28 » -> ("AMLOR", "5 MG", "COMPRIME", "BOITE DE 28")."""
    tokens = label.split()
    first = next((i for i in range(1, len(tokens)) if re.match(r"^\d", tokens[i])), None)
    if first is None:
        return label.strip(), None, None, None
    dosage, rest = _split_dosage(tokens[first:])
    tail = " ".join(rest)
    found = _PRESENTATION_RE.search(tail)
    if found:
        return " ".join(tokens[:first]), dosage, tail[:found.start()].strip() or None, tail[found.start():].strip()
    return " ".join(tokens[:first]), dosage, tail or None, None


def import_generics_file(db: Session, path: str | Path, *, edition: str | None = None, version_date: date | None = None,
                         create_missing: bool = True, method: str = "file") -> dict:
    mapping, rows = read_rows(path, GENERIC_COLUMNS, min_matches=3)
    with import_run(db, "ammps_generiques", file_path=path, method=method, version_date=version_date) as ctx:
        cache = RefCache(db)
        groups: dict[str, m.GenericGroup] = {}
        for line, row in rows:
            ctx.run.rows_read += 1
            group_label, spec = cell(row, mapping, "group"), cell(row, mapping, "specialty")
            member_type = str(cell(row, mapping, "type") or "").strip().upper()
            if not group_label or not spec or spec == "-" or member_type.startswith("GROUPE") or member_type in ("", "-"):
                ctx.reject("Ligne parasite ou incomplète ignorée", line)
                continue
            gkey = normalize_text(group_label)
            group = groups.get(gkey) or db.scalar(select(m.GenericGroup).where(m.GenericGroup.label_normalized == gkey))
            if group is None:
                group = m.GenericGroup(label=group_label, label_normalized=gkey, route=cell(row, mapping, "route"),
                                       register_edition=edition, data_status="official", source_id=ctx.source.id)
                db.add(group)
                db.flush()
            groups[gkey] = group
            substances, _, _ = parse_group_label(group_label)
            brand, dosage, form, presentation = parse_member_label(spec)
            lab = cell(row, mapping, "laboratory")
            code, ean_status = normalize_ean(cell(row, mapping, "ean"))
            if ean_status in ("invalid_checksum", "not_ean13"):
                ctx.warn(f"Code-barres {code} ({ean_status}) pour {spec}", line)
            med = db.scalar(select(m.Medicine).where(m.Medicine.source_record_key == medicine_key(brand, dosage, form)))
            method_used = "exact" if med else "unmatched"
            if med is None and create_missing and dosage:
                med, _ = upsert_medicine(ctx, cache, brand=brand, dosage=dosage, form_label=form, substances=substances,
                                         laboratory=lab, princeps=member_type[:1], data_status="official")
                method_used = "created"
            if med is not None and method_used == "exact" and med.source_id == ctx.source.id:
                method_used = "created"  # spécialité créée depuis le répertoire lors d'un import précédent
            pres = None
            if med is not None:
                if not med.princeps_status and member_type[:1] in ("P", "G", "I"):
                    med.princeps_status = member_type[:1]
                pres, _ = upsert_presentation(ctx, med, label=presentation, ean=code if ean_status == "valid" else None)
            rkey = normalize_text(spec)
            member = db.scalar(select(m.GenericGroupMember).where(m.GenericGroupMember.group_id == group.id,
                                                                  m.GenericGroupMember.raw_label_normalized == rkey))
            if member is None:
                member = m.GenericGroupMember(group_id=group.id, raw_label=spec, raw_label_normalized=rkey,
                                              member_type=member_type[:4], match_method=method_used)
                db.add(member)
                ctx.run.rows_inserted += 1
            else:
                ctx.run.rows_updated += 1
            member.medicine_id = med.id if med else None
            member.presentation_id = pres.id if pres else None
            member.laboratory_raw, member.ean13, member.ean_status = lab, code, ean_status
            member.match_method = method_used
            db.flush()
    return ctx.summary()
