"""Phase 1 (enrichissement) : analyse du répertoire, cohérence des équivalences, conditionnement, BDPM, priorité des
statuts, contrôle qualité et recherche par code-barres. Les fixtures créées ici utilisent des noms FICTIFS."""
import csv
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import models as m
from app.ingestion.aliases import import_aliases_file
from app.ingestion.bdpm import import_bdpm_compositions
from app.ingestion.common import parse_pack, strengths_equivalent
from app.ingestion.generics import import_generics_file, parse_member_label
from app.ingestion.medicines import import_medicines_file
from app.ingestion.quality import run_quality_checks
from app.ingestion.seed import seed_all
from app.main import app
from tests.conftest import ROOT


def _csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(header)
        w.writerows(rows)
    return path


@pytest.fixture
def client(seeded):
    with TestClient(app) as c:
        yield c


def test_member_label_uses_group_anchors():
    # anomalie réelle du répertoire : le « 5 » appartient au nom « FUSIDATE PHARMA 5 », le dosage est « 2% »
    assert parse_member_label("FUSIDATE PHARMA 5 2% CREME TUBE DE 15 G", "0,02", "CREME") == (
        "FUSIDATE PHARMA 5", "2%", "CREME", "TUBE DE 15 G")
    assert parse_member_label("A.V.T. 0,5 G / 0,002 G / 0,02 G COMPRIME EFFERVESCENT BOITE DE 10",
                              "0,5 G / 0,002 G / 0,02 G", "COMPRIME EFFERVESCENT")[1] == "0,5 G / 0,002 G / 0,02 G"


def test_strength_equivalence_never_confuses_doses():
    assert strengths_equivalent("0,5 G", "500 MG") is True
    assert strengths_equivalent("2%", "0,02") is True
    assert strengths_equivalent("500 MG", "50 MG") is False
    assert strengths_equivalent("80 MG / ML", "80 MG") is False          # concentration ≠ dose unitaire
    assert strengths_equivalent("1 G / 125 MG", "1 G / 62,5 MG") is False
    assert strengths_equivalent("250 MBQ / ML", "250 MG / ML") is False
    assert strengths_equivalent("UN COMPRIME", "500 MG") is None          # incomparable : rien n'est déduit


def test_pack_parsing_is_conservative():
    assert parse_pack("BOITE DE 28") == (Decimal("28"), None)
    assert parse_pack("TUBE DE 15 G") == (Decimal("15"), "g")
    assert parse_pack("BOITE DE 12 SACHETS") == (Decimal("12"), "sachet")
    assert parse_pack("BOITE DE 1 FLACON DE 120") == (None, None)
    assert parse_pack("BOITE DE 1 FLACON DE POUDRE ET 1 AMPOULE DE SOLVANT") == (None, None)


def test_seed_fixes_repertoire_dosage_and_structures_packs(seeded):
    db = seeded
    fus = db.scalar(select(m.Medicine).where(m.Medicine.brand_normalized == "fusidate pharma 5"))
    assert fus is not None and fus.dosage_text == "2%"
    assert db.scalar(select(func.count()).select_from(m.Medicine).where(m.Medicine.dosage_text == "5 2%")) == 0
    amlor = db.scalar(select(m.MedicinePresentation).where(m.MedicinePresentation.ean13 == "6118000480020"))
    assert amlor.pack_quantity == Decimal("28") and amlor.pack_unit is None
    clariscan = db.scalar(select(m.GenericGroupMember).where(m.GenericGroupMember.raw_label.like("CLARISCAN%")))
    assert clariscan.ean_status == "gtin14" and clariscan.medicine_id is not None
    assert db.scalar(select(m.MedicinePresentation.ean13).where(
        m.MedicinePresentation.id == clariscan.presentation_id)) is None  # GTIN-14 logistique jamais pris pour un EAN-13


def test_inconsistent_repertoire_member_is_not_linked(db, tmp_path):
    path = _csv(tmp_path / "rep.csv", ["GROUPE", "VOIE", "TYPE", "SPECIALITE", "EPI", "EAN 13"], [
        ["TESTOMEDINE 500 MG COMPRIME", "ORALE", "P", "TESTOMED 500 MG COMPRIME BOITE DE 10", "LABO TEST", "-"],
        ["TESTOMEDINE 500 MG COMPRIME", "ORALE", "G", "GENETEST 250 MG COMPRIME BOITE DE 10", "LABO TEST", "-"],
        ["TESTOMEDINE 500 MG COMPRIME", "ORALE", "G", "AUTRETEST 500 MG GELULE BOITE DE 10", "LABO TEST", "-"]])
    report = import_generics_file(db, path)
    assert report["warnings"] >= 2
    members = {x.raw_label.split()[0]: x for x in db.scalars(select(m.GenericGroupMember))}
    assert members["TESTOMED"].medicine_id is not None
    for name in ("GENETEST", "AUTRETEST"):  # dosage ou forme différents : pas d'équivalence réglementaire créée
        assert members[name].medicine_id is None and members[name].match_method == "inconsistent"
    assert db.scalar(select(func.count()).select_from(m.Medicine)) == 1


def test_simulated_row_never_attaches_to_official_medicine(db, tmp_path):
    header = ["SPECIALITE", "DOSAGE", "FORME", "PRESENTATION", "SUBSTANCE ACTIVE", "PPV"]
    real = _csv(tmp_path / "real.csv", header, [["TESTOMED", "500 MG", "COMPRIME", "BOITE DE 10", "TESTOMEDINE", "12,50"]])
    demo = _csv(tmp_path / "demo.csv", header, [["TESTOMED", "500 MG", "COMPRIME", "BOITE DE 99", "TESTOMEDINE", "1,00"]])
    import_medicines_file(db, real, version_date=date(2026, 10, 1))
    report = import_medicines_file(db, demo, source_code="demo_simulated", data_status="simulated")
    assert report["rejected"] == 1
    med = db.scalar(select(m.Medicine).where(m.Medicine.brand_name == "TESTOMED"))
    assert med.data_status == "official" and [p.label for p in med.presentations] == ["BOITE DE 10"]


def test_bdpm_enriches_search_terms_only_for_known_substances(seeded, tmp_path):
    db = seeded
    n_before = db.scalar(select(func.count()).select_from(m.ActiveIngredient))
    lines = ["60000001\tcomprimé\t39727\tAMLODIPINE\t5 mg\tun comprimé\tFT\t1",
             "60000001\tcomprimé\t93748\tBÉSILATE D'AMLODIPINE\t\t\tSA\t1",
             "60000002\tcomprimé\t11111\tSUBSTANCEFRANCAISE\t10 mg\tun comprimé\tSA\t1",
             # faux positifs observés dans le fichier réel : composé différent, sel d'une autre forme saline
             "60000003\tcomprimé\t48694\tTHIAMINE\t1 mg\tun comprimé\tFT\t1",
             "60000003\tcomprimé\t99999\tCOCARBOXYLASE TÉTRAHYDRATÉ\t\t\tSA\t1",
             "60000004\tcomprimé\t01785\tÉRYTHROMYCINE\t1 mg\tun comprimé\tFT\t1",
             "60000004\tcomprimé\t88888\tLACTOBIONATE D'ÉRYTHROMYCINE\t\t\tSA\t1"]
    path = tmp_path / "CIS_COMPO_bdpm.txt"
    path.write_bytes("\r\n".join(lines).encode("latin-1"))
    report = import_bdpm_compositions(db, path, version_date=date(2026, 9, 29))
    assert report["ingredients_enriched"] == 2  # amlodipine (sel + code) et thiamine (code seulement)
    thiamine = db.scalar(select(m.ActiveIngredient).where(m.ActiveIngredient.name == "THIAMINE"))
    assert thiamine.search_terms == [] and thiamine.external_codes == {"bdpm_substance": "48694"}
    ery = db.scalar(select(m.ActiveIngredient).where(m.ActiveIngredient.name == "ERYTHROMYCINE (ETHYLSUCCINATE)"))
    assert not ery.search_terms and not ery.external_codes
    aml = db.scalar(select(m.ActiveIngredient).where(m.ActiveIngredient.name == "AMLODIPINE"))
    assert aml.search_terms == ["BÉSILATE D'AMLODIPINE"] and aml.external_codes == {"bdpm_substance": "39727"}
    assert "BÉSILATE D'AMLODIPINE" not in (aml.synonyms or [])  # jamais utilisé pour résoudre une substance
    assert db.scalar(select(func.count()).select_from(m.ActiveIngredient)) == n_before
    src = db.scalar(select(m.DataSource).where(m.DataSource.code == "bdpm_fr"))
    assert src.market == "FR" and src.default_data_status == "reference"
    amlor = db.scalar(select(m.Medicine).where(m.Medicine.brand_normalized == "amlor", m.Medicine.dosage_text == "5 MG"))
    assert "besilate d amlodipine" in amlor.search_text
    assert import_bdpm_compositions(db, path)["ingredients_enriched"] == 0  # idempotent


def test_aliases_require_reference_and_existing_medicine(seeded, tmp_path):
    db = seeded
    path = _csv(tmp_path / "aliases.csv", ["SPECIALITE", "DOSAGE", "FORME", "ALIAS", "LANGUE", "TYPE", "SOURCE REFERENCE"], [
        ["AMLOR", "5 MG", "COMPRIME", "أملور", "ar", "", "Photo d'emballage de test"],
        ["AMLOR", "5 MG", "COMPRIME", "AMLORTEST", "fr", "brand_variant", ""],
        ["INEXISTANT", "5 MG", "COMPRIME", "X", "fr", "", "ref"]])
    report = import_aliases_file(db, path)
    assert report["inserted"] == 1 and report["rejected"] == 2
    alias = db.scalar(select(m.MedicineAlias))
    assert alias.kind == "arabic_script" and alias.data_status == "unverified"


def test_quality_checks_pass_on_seed_and_detect_violations(seeded):
    db = seeded
    report = run_quality_checks(db, today=date(2026, 10, 26))
    by_code = {c["code"]: c for c in report["checks"]}
    assert report["critical"] == 0, [c for c in report["checks"] if c["severity"] == "critical" and c["count"]]
    assert by_code["generic_member_unlinked"]["count"] == 0
    # violation provoquée : présentation simulée glissée sous une fiche officielle, EAN invalide et prix sans date
    med = db.scalar(select(m.Medicine).where(m.Medicine.data_status == "official"))
    sim = db.scalar(select(m.DataSource).where(m.DataSource.code == "demo_simulated"))
    db.add(m.MedicinePresentation(medicine_id=med.id, label="FICTIF", label_normalized="fictif", data_status="simulated",
                                  source_id=sim.id, price_status="unknown", ean13="6118000140671"))
    db.add(m.MedicinePresentation(medicine_id=med.id, label="SANS DATE", label_normalized="sans date",
                                  data_status="official", source_id=med.source_id, price_status="priced",
                                  ppv_mad=Decimal("9.99")))
    db.flush()
    by_code = {c["code"]: c for c in run_quality_checks(db)["checks"]}
    for code in ("simulated_presentation_on_real_medicine", "invalid_ean_stored", "price_without_date"):
        assert by_code[code]["count"] == 1, code
    db.rollback()


def test_seed_twice_keeps_quality_and_counts(seeded):
    db = seeded
    seed_all(db, ROOT / "data")
    assert run_quality_checks(db)["critical"] == 0
    assert db.scalar(select(func.count()).select_from(m.MedicinePresentation).where(
        m.MedicinePresentation.ean13 == "6118000480020")) == 1


def test_search_by_barcode_is_exact(client):
    data = client.get("/api/medicines/search", params={"q": "6118000480020"}).json()
    assert data["meta"]["matched_by"] == "barcode"
    assert [(i["brand"], i["dosage"]) for i in data["items"]] == [("AMLOR", "5 MG")]
    gtin = client.get("/api/medicines/search", params={"q": "06118000480020"}).json()  # DataMatrix
    assert [i["brand"] for i in gtin["items"]] == ["AMLOR"]
    wrong = client.get("/api/medicines/search", params={"q": "6118000480021"}).json()  # clé fausse : aucun voisin proposé
    assert wrong["items"] == [] and wrong["meta"]["ean_status"] == "invalid_checksum"


def test_search_typo_keeps_requested_dosage_on_official_data(client):
    data = client.get("/api/medicines/search", params={"q": "amlorr 10 mg"}).json()
    assert data["items"][0]["brand"] == "AMLOR" and data["meta"]["did_you_mean"] == "AMLOR"
    assert {i["dosage"] for i in data["items"]} == {"10 MG"}  # même substance possible, jamais un autre dosage
    none = client.get("/api/medicines/search", params={"q": "amlor 20 mg"}).json()
    assert none["items"] == [] and set(none["meta"]["available_dosages"]) == {"5 MG", "10 MG"}


def test_sources_expose_market_and_reuse_conditions(client):
    sources = {s["code"]: s for s in client.get("/api/sources").json()}
    assert sources["ammps_medicaments"]["market"] == "MA" and sources["demo_simulated"]["default_data_status"] == "simulated"
    assert "tous droits réservés" in sources["ammps_medicaments"]["reuse_conditions"]


def test_card_min_price_ignores_simulated_presentations(client, seeded):
    db = seeded
    avt = db.scalar(select(m.Medicine).where(m.Medicine.brand_normalized == "a v t"))
    sim = db.scalar(select(m.DataSource).where(m.DataSource.code == "demo_simulated"))
    db.add(m.MedicinePresentation(medicine_id=avt.id, label="FICTIF", label_normalized="fictif", data_status="simulated",
                                  source_id=sim.id, price_status="priced", ppv_mad=Decimal("1.00")))
    db.commit()
    card = client.get(f"/api/medicines/{avt.id}").json()
    assert card["min_ppv"] == 10.7
