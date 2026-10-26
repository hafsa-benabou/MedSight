"""Enrichissement terminologique depuis la BDPM (France, Licence Ouverte Etalab 2.0) : fichier CIS_COMPO_bdpm.txt.

Usage strictement contrôlé :
- seules les substances DÉJÀ présentes dans la base marocaine sont enrichies (aucune substance créée) ;
- la BDPM relie, pour une même spécialité (CIS) et un même numéro de liaison, la substance active telle qu'écrite
  (SA, souvent un sel : « BÉSILATE D'AMLODIPINE ») à sa fraction thérapeutique (FT : « AMLODIPINE ») ;
- le nom du sel est ajouté aux `search_terms` de la substance (recherche et NLP) et non à ses `synonyms` : un dosage
  exprimé en sel n'est pas un dosage en base, la résolution des substances à l'import n'est donc jamais modifiée ;
- aucune spécialité, présentation, prix ou dosage français n'est importé (marchés distincts).

Format (description officielle « Contenu et format des fichiers téléchargeables », v5) : texte tabulé, encodage
Latin-1, 8 colonnes : CIS, élément pharmaceutique, code substance, dénomination, dosage, référence du dosage,
nature du composant (SA | FT), numéro de liaison SA/FT."""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models as m
from app.ingestion.common import import_run, refresh_search_text
from app.nlp.text import normalize_text

COLUMNS = ("cis", "element", "substance_code", "name", "dosage", "dosage_ref", "nature", "link")


def read_bdpm_compositions(path: str | Path) -> list[dict[str, str]]:
    raw = Path(path).read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    rows = []
    for values in csv.reader(text.splitlines(), delimiter="\t", quoting=csv.QUOTE_NONE):
        if len(values) < 8:
            continue
        rows.append(dict(zip(COLUMNS, (v.strip() for v in values[:8]))))
    return rows


def salt_pairs(rows: list[dict[str, str]]) -> dict[str, dict[str, set[str]]]:
    """{fraction thérapeutique normalisée: {"names": {sels}, "codes": {codes substance FT}}}."""
    linked: dict[tuple[str, str], dict[str, list[dict[str, str]]]] = defaultdict(lambda: {"SA": [], "FT": []})
    for r in rows:
        if r["nature"] in ("SA", "FT"):
            linked[(r["cis"], r["link"])][r["nature"]].append(r)
    out: dict[str, dict[str, set[str]]] = defaultdict(lambda: {"names": set(), "codes": set()})
    for group in linked.values():
        if len(group["FT"]) != 1:
            continue  # liaison ambiguë : ignorée plutôt que devinée
        ft = group["FT"][0]
        key = normalize_text(ft["name"])
        out[key]["codes"].add(ft["substance_code"])
        for sa in group["SA"]:
            if normalize_text(sa["name"]) != key:
                out[key]["names"].add(sa["name"].upper())
    return out


def import_bdpm_compositions(db: Session, path: str | Path, *, version_date: date | None = None) -> dict:
    rows = read_bdpm_compositions(path)
    pairs = salt_pairs(rows)
    with import_run(db, "bdpm_fr", file_path=path, method="file", version_date=version_date) as ctx:
        ctx.run.rows_read = len(rows)
        enriched: list[dict] = []
        touched: list[int] = []
        ingredients = list(db.scalars(select(m.ActiveIngredient)))
        other_terms = {ing.id: {ing.name_normalized} | {normalize_text(s) for s in ing.synonyms or []} for ing in ingredients}
        for ing in ingredients:
            # Règles strictes (vérifiées sur le fichier réel) : correspondance sur le nom exact seulement (les synonymes
            # élargiraient « ERYTHROMYCINE (ETHYLSUCCINATE) » au lactobionate) ; le sel doit contenir ce nom (écarte
            # « COCARBOXYLASE » pour la thiamine, « DOTA » pour l'acide gadotérique) ; un terme désignant une autre
            # substance de la base est écarté (« ACÉTYLSALICYLATE DE LYSINE » n'est pas l'acide acétylsalicylique).
            pair = pairs.get(ing.name_normalized)
            if pair is None:
                continue
            foreign = set().union(*(t for i, t in other_terms.items() if i != ing.id))
            names = {n for n in pair["names"] if ing.name_normalized in normalize_text(n)
                     and not any(f in normalize_text(n) for f in foreign if len(f) >= 6)}
            codes = pair["codes"]
            current = list(ing.search_terms or [])
            known = {normalize_text(t) for t in current} | other_terms[ing.id]
            added = sorted(n for n in names if normalize_text(n) not in known)
            ext = dict(ing.external_codes or {})
            new_code = ",".join(sorted(codes))
            if not added and ext.get("bdpm_substance") == new_code:
                continue
            ing.search_terms = current + added
            ext["bdpm_substance"] = new_code
            ing.external_codes = ext
            enriched.append({"ingredient": ing.name, "added_search_terms": added, "bdpm_substance": new_code})
            touched.append(ing.id)
            if added:
                ctx.run.rows_updated += 1
        db.flush()
        if touched:
            meds = db.scalars(select(m.Medicine).join(m.MedicineIngredient)
                              .where(m.MedicineIngredient.ingredient_id.in_(touched))
                              .options(selectinload(m.Medicine.ingredients).selectinload(m.MedicineIngredient.ingredient),
                                       selectinload(m.Medicine.aliases), selectinload(m.Medicine.form))).unique()
            for med in meds:
                refresh_search_text(med)
        for e in enriched[:300]:
            ctx.issues.append({"row": None, "level": "info",
                               "message": f"{e['ingredient']} : +{len(e['added_search_terms'])} terme(s) BDPM "
                                          f"{e['added_search_terms']} (code {e['bdpm_substance']})"})
    summary = ctx.summary()
    summary["ingredients_enriched"] = len(enriched)
    return summary
