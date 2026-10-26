"""Pipeline de données : parsing, provenance, priorité des sources, anomalies, idempotence, données simulées.
Les fixtures créées ici utilisent des noms FICTIFS (TESTOMED, ALPHAZINE…) et ne sont jamais chargées dans l'application."""
import csv
import json
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app import models as m
from app.core.ean import ean13_is_valid, normalize_ean
from app.ingestion.cnops import import_cnops_file
from app.ingestion.common import canonical_form, marketed_flag, parse_price, split_strengths
from app.ingestion.generics import parse_member_label
from app.ingestion.interactions import import_interactions_file
from app.ingestion.medicines import import_medicines_file
from app.ingestion.pharmacies import import_ammps_pharmacies, import_duty_shifts, import_osm_json
from app.ingestion.rcp import import_rcp_file
from app.ingestion.seed import purge_simulated, seed_all
from tests.conftest import ROOT


def _csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(header)
        w.writerows(rows)
    return path


def test_price_parsing_handles_ammps_formats():
    assert parse_price("4.303.00 DH") == (Decimal("4303.00"), "priced")
    assert parse_price("10,70 DH") == (Decimal("10.70"), "priced")
    assert parse_price("SANS PPV DH") == (None, "no_price")
    assert parse_price(None) == (None, "unknown")


def test_strengths_forms_and_status():
    s = split_strengths("0,5 G / 0,002 G / 0,02 G", 3)
    assert [x.mg for x in s] == [Decimal("500.0"), Decimal("2.000"), Decimal("20.00")]
    assert split_strengths("250 MBQ / ML", 1)[0].unit == "MBq/ml"
    assert canonical_form("COMPRIME PELLICULE SECABLE") == "comprime"
    assert canonical_form("GRANULE POUR SUSPENSION BUVABLE") == "suspension_buvable"
    assert marketed_flag("Commercialisé AO") is True and marketed_flag("AMM sans prix") is False


def test_ean13_validation():
    assert ean13_is_valid("6118000480020")
    assert normalize_ean("6118000140671")[1] == "invalid_checksum"
    assert normalize_ean("27037960641780") == ("27037960641780", "gtin14")  # CLARISCAN : GTIN-14 logistique valide
    assert normalize_ean("06118000480020") == ("6118000480020", "valid")    # DataMatrix : « 0 » + EAN-13
    assert normalize_ean("27037960641781")[1] == "invalid_checksum"
    assert normalize_ean("611800048002")[1] == "not_ean13"
    assert normalize_ean("-") == (None, "missing")


def test_member_label_parsing():
    assert parse_member_label("AMLOR 5 MG COMPRIME BOITE DE 28") == ("AMLOR", "5 MG", "COMPRIME", "BOITE DE 28")
    assert parse_member_label("ZOVIRAX 0,05 CREME DERMIQUE TUBE DE 2 G")[3] == "TUBE DE 2 G"


def test_seed_joins_sources_and_reports_anomalies(seeded):
    db = seeded
    avt = db.scalars(select(m.MedicinePresentation).join(m.Medicine).where(m.Medicine.brand_normalized == "a v t")).all()
    assert {p.label: (p.ppv_mad, p.ean13) for p in avt} == {
        "BOITE DE 10": (Decimal("10.70"), "6118000031055"), "BOITE DE 20": (Decimal("19.10"), "6118000031062")}
    assert all(p.data_status == "official" and p.price_as_of == date(2026, 10, 1) for p in avt)
    run = db.scalar(select(m.DataImport).join(m.DataSource).where(m.DataSource.code == "ammps_generiques"))
    messages = " ".join(i["message"] for i in run.report["issues"])
    assert run.rows_rejected == 1 and "invalid_checksum" in messages and "gtin14" in messages
    assert db.scalar(select(func.count()).where(m.MedicinePresentation.ean13 == "6118000140671")) == 0
    thiamine = db.scalar(select(m.ActiveIngredient).where(m.ActiveIngredient.name == "THIAMINE"))
    assert db.scalar(select(func.count()).where(m.MedicineIngredient.ingredient_id == thiamine.id)) == 1


def test_seed_is_idempotent(seeded):
    db = seeded
    tables = (m.Medicine, m.MedicinePresentation, m.GenericGroupMember, m.Pharmacy, m.PharmacyInventory, m.PharmacyDutyShift)
    before = {t.__tablename__: db.scalar(select(func.count()).select_from(t)) for t in tables}
    seed_all(db, ROOT / "data")
    assert before == {t.__tablename__: db.scalar(select(func.count()).select_from(t)) for t in tables}


def test_simulated_data_is_flagged_and_purgeable(seeded):
    db = seeded
    sim = db.scalars(select(m.Medicine).where(m.Medicine.data_status == "simulated")).all()
    assert "DOLIPRANE" in {x.brand_name for x in sim}
    assert all(p.address == "Adresse fictive (démo)" for p in db.scalars(select(m.Pharmacy).where(m.Pharmacy.data_status == "simulated")))
    assert all(i.is_simulated for i in db.scalars(select(m.PharmacyInventory)))
    purge_simulated(db)
    for model in (m.Medicine, m.Pharmacy, m.PharmacyInventory, m.PharmacyDutyShift):
        assert db.scalar(select(func.count()).select_from(model).where(model.data_status == "simulated")) == 0
    assert db.scalar(select(func.count()).select_from(m.Medicine).where(m.Medicine.data_status == "official")) > 0


def test_older_cnops_price_never_overrides_recent_ammps_price(db, tmp_path):
    from openpyxl import Workbook
    ammps = _csv(tmp_path / "ammps.csv", ["SPECIALITE", "DOSAGE", "FORME", "PRESENTATION", "SUBSTANCE ACTIVE", "PPV", "PH"],
                 [["TESTOMED", "500 MG", "COMPRIME", "BOITE DE 10", "TESTOMEDINE", "12,50", "8,00"]])
    import_medicines_file(db, ammps, version_date=date(2026, 10, 1))
    wb = Workbook()
    ws = wb.active
    ws.append(["Référentiel des médicaments (fixture de test)"])
    ws.append([])
    ws.append(["NOM", "DCI1", "DOSAGE1", "UNITE_DOSAGE1", "FORME", "PRESENTATION", "PPV", "PH", "PRIX_BR", "PRINCEPS_GENERIQUE", "TAUX_REMBOURSEMENT"])
    ws.append(["TESTOMED", "TESTOMEDINE", 500, "MG", "COMPRIME", "BOITE DE 10", 9.9, 6.1, 8.0, "P", 0.7])
    ws.append(["AUTREMED", "AUTREMEDINE", 1, "G", "SACHET", "BOITE DE 6", 30, 20, 25, "G", 70])
    path = tmp_path / "cnops.xlsx"
    wb.save(path)
    assert import_cnops_file(db, path, dry_run=True)["rows"] == 2
    report = import_cnops_file(db, path, version_date=date(2014, 1, 1))
    assert report["rows_read"] == 2 and report["rejected"] == 0
    pres = db.scalar(select(m.MedicinePresentation).join(m.Medicine).where(m.Medicine.brand_name == "TESTOMED"))
    assert pres.ppv_mad == Decimal("12.50") and pres.price_as_of == date(2026, 10, 1)
    reimb = db.scalar(select(m.Reimbursement).where(m.Reimbursement.raw_name == "TESTOMED"))
    assert reimb.base_remboursement_mad == Decimal("8.00") and reimb.taux_remboursement == Decimal("70.0")
    assert reimb.ppv_reference_mad == Decimal("9.90") and reimb.valid_as_of == date(2014, 1, 1)
    # prix CNOPS 2014 : conservé comme référence historique datée, jamais comme prix courant de la présentation
    other = db.scalar(select(m.MedicinePresentation).join(m.Medicine).where(m.Medicine.brand_name == "AUTREMED"))
    assert other.ppv_mad is None and other.price_status == "unknown"
    other_reimb = db.scalar(select(m.Reimbursement).where(m.Reimbursement.raw_name == "AUTREMED"))
    assert other_reimb.ppv_reference_mad == Decimal("30.00") and other_reimb.valid_as_of == date(2014, 1, 1)
    import_cnops_file(db, path, version_date=date(2014, 1, 1))  # ré-import : idempotent
    assert db.scalar(select(func.count()).select_from(m.Reimbursement)) == 2


def test_rcp_pdf_sections_keep_source(db, tmp_path):
    from reportlab.pdfgen import canvas
    med_file = _csv(tmp_path / "m.csv", ["SPECIALITE", "DOSAGE", "FORME", "SUBSTANCE ACTIVE"], [["TESTOMED", "500 MG", "COMPRIME", "TESTOMEDINE"]])
    import_medicines_file(db, med_file)
    med = db.scalar(select(m.Medicine).where(m.Medicine.brand_name == "TESTOMED"))
    pdf = tmp_path / "rcp.pdf"
    c = canvas.Canvas(str(pdf))
    y = 800
    for line in ["4. DONNEES CLINIQUES", "4.1. Indications thérapeutiques", "Texte de test indications.",
                 "4.2. Posologie et mode d'administration", "Texte de test posologie.", "4.8. Effets indésirables",
                 "Texte de test effets.", "5. PROPRIETES PHARMACOLOGIQUES", "Hors périmètre."]:
        c.drawString(50, y, line)
        y -= 20
    c.save()
    report = import_rcp_file(db, pdf, medicine_id=med.id, source_url="https://exemple.test/rcp.pdf")
    assert report["sections"] == ["indications", "posology", "side_effects"]
    posology = db.scalar(select(m.ClinicalSection).where(m.ClinicalSection.section_code == "posology"))
    assert posology.content == "Texte de test posologie." and posology.data_status == "unverified"
    assert posology.source_url == "https://exemple.test/rcp.pdf" and posology.extraction_method == "rcp_pdf_parser"


def test_interactions_reject_unknown_substances_and_order_pairs(db, tmp_path):
    med_file = _csv(tmp_path / "m.csv", ["SPECIALITE", "DOSAGE", "FORME", "SUBSTANCE ACTIVE"],
                    [["A-TEST", "1 MG", "COMPRIME", "ALPHAZINE"], ["B-TEST", "1 MG", "COMPRIME", "BETAMOL"]])
    import_medicines_file(db, med_file)
    ddi = _csv(tmp_path / "ddinter.csv", ["DDInterID_A", "Drug_A", "DDInterID_B", "Drug_B", "Level"],
               [["X1", "Betamol", "X2", "Alphazine", "Major"], ["X1", "Alphazine", "X3", "Unknownium", "Minor"]])
    report = import_interactions_file(db, ddi, source_code="ddinter")
    assert report["inserted"] == 1 and report["rejected"] == 1
    inter = db.scalar(select(m.DrugInteraction))
    assert inter.ingredient_a_id < inter.ingredient_b_id
    assert inter.severity == "major" and inter.data_status == "reference"
    assert db.scalar(select(func.count()).select_from(m.ActiveIngredient)) == 2  # jamais de substance créée


def test_osm_import_assigns_city_and_checks_registry(db, tmp_path):
    reg = _csv(tmp_path / "reg.csv", ["NOM DE LA PHARMACIE", "VILLE"], [["PHARMACIE TESTALPHA", "CASABLANCA"]])
    import_ammps_pharmacies(db, reg)
    osm = {"elements": [
        {"type": "node", "id": 1, "lat": 33.57, "lon": -7.59, "tags": {"place": "city", "name": "Casablanca"}},
        {"type": "node", "id": 2, "lat": 33.58, "lon": -7.60, "tags": {"amenity": "pharmacy", "name": "Pharmacie Testalpha", "phone": "+212 5 00 00 00 00"}},
        {"type": "way", "id": 3, "center": {"lat": 10.0, "lon": 10.0}, "tags": {"amenity": "pharmacy", "name": "Pharmacie Testbeta"}},
        {"type": "node", "id": 4, "tags": {"amenity": "pharmacy", "name": "Sans coordonnées"}}]}
    path = tmp_path / "osm.json"
    path.write_text(json.dumps(osm), encoding="utf-8")
    report = import_osm_json(db, path)
    assert report["inserted"] == 2 and report["rejected"] == 1
    alpha = db.scalar(select(m.Pharmacy).where(m.Pharmacy.source_record_key == "osm:node/2"))
    assert alpha.city == "Casablanca" and alpha.in_ammps_registry is True and alpha.data_status == "unverified"
    beta = db.scalar(select(m.Pharmacy).where(m.Pharmacy.source_record_key == "osm:way/3"))
    assert beta.city is None and beta.latitude == 10.0


def test_duty_import_rejects_incoherent_rows(db, tmp_path):
    path = _csv(tmp_path / "garde.csv", ["PHARMACY NAME", "CITY", "SHIFT TYPE", "STARTS AT", "ENDS AT", "SOURCE URL"],
                [["Pharmacie Testgamma", "rabat", "nuit", "2026-10-25 20:00", "2026-10-26 09:00", "https://exemple.test/garde"],
                 ["Pharmacie Testdelta", "rabat", "nuit", "2026-10-26 09:00", "2026-10-25 20:00", ""]])
    report = import_duty_shifts(db, path)
    assert report["inserted"] == 1 and report["rejected"] == 1
    shift = db.scalar(select(m.PharmacyDutyShift))
    assert shift.city == "Rabat" and shift.ends_at > shift.starts_at and shift.data_status == "unverified"
