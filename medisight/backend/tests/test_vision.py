"""Pill Identifier : validation des images, qualité, codes-barres (réellement décodés), extraction, matching, API.

Les images sont SYNTHÉTIQUES (texte et codes-barres générés) et l'OCR est SIMULÉ par FakeOcr : ces tests vérifient
la logique, pas la qualité de reconnaissance sur de vraies photos. Les tests avec le vrai Tesseract sont dans
test_vision_tesseract.py ; la validation sur photos réelles se fait avec `cli evaluate-identifier` (corpus)."""
import io

import numpy as np
import pytest
import zxingcpp
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from sqlalchemy import func, select

from app import models as m
from app.core.config import get_settings
from app.core.errors import AppError
from app.main import app, get_ocr_engine
from app.vision.barcodes import _interpret, parse_gs1, read_barcodes
from app.vision.extraction import Vocabulary, extract
from app.vision.identify import identify_image
from app.vision.images import load_image, sniff_format
from app.vision.ocr import DisabledEngine, OcrResult, OcrWord, group_lines
from app.vision.preprocess import assess_quality

AMLOR_5_28 = "6118000480020"
VALID_UNKNOWN = "6111234567895"  # clé GS1 valide, absent du catalogue


class FakeOcr:
    """OCR simulé : renvoie les lignes fournies (confiance 90), quelle que soit l'image."""
    name = "fake"

    def __init__(self, lines: list[str]):
        self.lines = lines

    def status(self) -> dict:
        return {"available": True, "engine": self.name, "languages": "fra+ara+eng", "version": "test"}

    def read(self, image) -> OcrResult:
        words = []
        for i, line in enumerate(self.lines):
            x = 10
            for token in line.split():
                words.append(OcrWord(token, 90.0, (x, 60 * i, 20 * len(token), 50 - 4 * i), (1, 1, i)))
                x += 20 * len(token) + 10
        return OcrResult(words, group_lines(words), self.name, "fra+ara+eng")


def box_image(text_lines=("BOITE",), barcode: str | None = None, fmt="PNG", size=(1200, 900), datamatrix=None) -> bytes:
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=64)
    for i, line in enumerate(text_lines):
        draw.text((60, 60 + 90 * i), line, fill="black", font=font)
    if barcode:
        bc = Image.fromarray(np.array(zxingcpp.create_barcode(barcode, zxingcpp.BarcodeFormat.EAN13).to_image(scale=4)))
        img.paste(bc.convert("RGB"), (60, size[1] - bc.height - 60))
    if datamatrix:
        dm = Image.fromarray(np.array(zxingcpp.create_barcode(datamatrix, zxingcpp.BarcodeFormat.DataMatrix).to_image(scale=8)))
        img.paste(dm.convert("RGB"), (size[0] - dm.width - 80, size[1] - dm.height - 80))
    buf = io.BytesIO()
    img.save(buf, fmt)
    return buf.getvalue()


@pytest.fixture
def settings(tmp_path):
    return get_settings().model_copy(update={"data_dir": tmp_path, "store_uploaded_images": False})


def run(db, data, lines, settings, **upd):
    return identify_image(db, data, settings.model_copy(update=upd), FakeOcr(lines) if lines is not None else DisabledEngine())


# ---------- 1-4. Réception et validation ----------

def test_valid_formats_are_decoded(settings):
    for fmt, name in (("PNG", "png"), ("JPEG", "jpeg"), ("WEBP", "webp")):
        img = load_image(box_image(fmt=fmt), settings)
        assert img.format == name and (img.width, img.height) == (1200, 900) and img.bgr.shape == (900, 1200, 3)


def test_exif_orientation_is_applied_and_metadata_dropped(settings):
    src = Image.new("RGB", (800, 400), "white")
    exif = src.getexif()
    exif[0x0112] = 6  # rotation de 90° demandée par le téléphone
    buf = io.BytesIO()
    src.save(buf, "JPEG", exif=exif)
    img = load_image(buf.getvalue(), settings)
    assert (img.width, img.height) == (400, 800) and img.orientation_corrected


def test_corrupted_image_is_rejected(settings):
    data = box_image(fmt="JPEG")
    with pytest.raises(AppError) as err:
        load_image(data[: len(data) // 3], settings)
    assert err.value.code == "corrupted_image" and err.value.status_code == 422


def test_non_image_files_are_rejected(settings):
    for data in (b"%PDF-1.7 faux document", b"GIF89a....", "texte.jpg".encode() * 20):
        with pytest.raises(AppError) as err:
            load_image(data, settings)
        assert err.value.status_code == 415
    assert sniff_format(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "webp"


def test_oversized_file_and_pixel_bomb_are_rejected(settings):
    with pytest.raises(AppError) as err:
        load_image(box_image(), settings.model_copy(update={"max_upload_mb": 0.001}))
    assert err.value.code == "file_too_large" and err.value.status_code == 413
    with pytest.raises(AppError) as err:
        load_image(box_image(size=(3000, 3000)), settings.model_copy(update={"max_image_pixels": 1_000_000}))
    assert err.value.code == "image_too_large"


def test_large_image_is_downscaled(settings):
    img = load_image(box_image(size=(4000, 3000), fmt="JPEG"), settings)
    assert max(img.width, img.height) == settings.max_image_side and img.downscaled


def test_quality_detects_blur_and_low_resolution(settings):
    sharp = load_image(box_image(("AMLOR 5 MG",)), settings)
    assert assess_quality(sharp.bgr, 320).usable
    blurred = Image.open(io.BytesIO(box_image(("AMLOR 5 MG",)))).filter(ImageFilter.GaussianBlur(14))
    buf = io.BytesIO()
    blurred.save(buf, "PNG")
    q = assess_quality(load_image(buf.getvalue(), settings).bgr, 320)
    assert not q.usable and "image_tres_floue" in q.issues
    tiny = assess_quality(load_image(box_image(size=(200, 150)), settings).bgr, 320)
    assert "resolution_insuffisante" in tiny.issues


# ---------- Codes-barres (décodage réel par zxing-cpp) ----------

def test_barcode_reader_reads_ean13_and_gs1_datamatrix(settings):
    img = load_image(box_image(barcode=AMLOR_5_28, datamatrix="(01)0" + AMLOR_5_28 + "(17)281231(10)LOT7"), settings)
    reads = {b.format: b for b in read_barcodes(img.bgr)}
    assert reads["EAN13"].code == AMLOR_5_28 and reads["EAN13"].status == "valid"
    assert reads["DataMatrix"].code == AMLOR_5_28 and reads["DataMatrix"].gs1["17"] == "281231"


def test_invalid_codes_are_never_corrected():
    bad = _interpret("EAN13", "6118000480021", "test")
    assert bad.status == "invalid_checksum" and bad.code == "6118000480021"
    assert _interpret("ITF", "27037960641780", "test").status == "gtin14"
    assert parse_gs1("\x1d0106118000480020\x1d10AB") == {"01": "06118000480020", "10": "AB"}


# ---------- 5-13. Identification ----------

def test_barcode_in_catalog_with_corroborating_text_is_identified(seeded, settings):
    r = run(seeded, box_image(barcode=AMLOR_5_28), ["AMLOR 5 mg", "28 comprimés"], settings)
    assert r["status"] == "identified" and r["reliability"] == "high" and r["identified_level"] == "presentation"
    top = r["candidates"][0]
    assert (top["brand"], top["dosage"], top["presentation"]) == ("AMLOR", "5 MG", "BOITE DE 28")
    assert top["evidence"]["barcode"] == "match" and top["evidence"]["pack"] == "match"
    assert r["presentation_ids"][0] == top["presentation_id"] and top["source"]["code"] == "ammps_generiques"
    assert r["barcodes"][0]["in_catalog"] is True and "probabilit" in r["score_note"]


def test_barcode_only_is_identified_with_warning(seeded, settings):
    r = run(seeded, box_image(barcode=AMLOR_5_28), [], settings)
    assert r["status"] == "identified" and r["reliability"] == "medium"
    assert any("seul code-barres" in w for w in r["warnings"])


def test_valid_barcode_absent_from_catalog_falls_back_to_ocr(seeded, settings):
    r = run(seeded, box_image(barcode=VALID_UNKNOWN), ["AMLOR 10 mg", "28 comprimés"], settings)
    assert any("absent du catalogue" in w for w in r["warnings"])
    assert r["status"] == "identified" and r["candidates"][0]["dosage"] == "10 MG"
    assert r["candidates"][0]["evidence"]["barcode"] == "unknown"  # code inconnu du catalogue : ne contredit rien


def test_invalid_printed_digits_are_ignored(seeded, settings):
    r = run(seeded, box_image(), ["AMLOR 5 mg", "6118000480021"], settings)
    assert any("clé de contrôle invalide" in w for w in r["warnings"])
    assert all(c["evidence"]["barcode"] != "match" for c in r["candidates"])


def test_ocr_typo_is_tolerated_without_changing_dosage(seeded, settings):
    r = run(seeded, box_image(), ["AMLORR", "10 mg", "comprimé"], settings)
    assert r["status"] == "identified"
    assert {(c["brand"], c["dosage"]) for c in r["candidates"]} == {("AMLOR", "10 MG")}


def test_correct_name_with_absent_dosage_is_never_substituted(seeded, settings):
    r = run(seeded, box_image(), ["AMLOR", "20 mg", "comprimés"], settings)
    assert r["status"] == "not_found" and r["candidates"] == []
    assert r["available_dosages"] == ["10 MG", "5 MG"] and "aucune autre dose" in " ".join(r["reasons"])


def test_unknown_pack_lists_every_possible_presentation(seeded, settings):
    r = run(seeded, box_image(), ["AMLOR", "5 mg", "comprimés"], settings)
    assert r["status"] == "identified" and r["identified_level"] == "medicine"
    assert sorted(c["presentation"] for c in r["candidates"]) == ["BOITE DE 14", "BOITE DE 28"]
    r14 = run(seeded, box_image(), ["AMLOR 5 mg", "14 comprimés"], settings)
    assert r14["identified_level"] == "presentation" and r14["candidates"][0]["presentation"] == "BOITE DE 14"


def test_different_pack_is_a_contradiction_not_a_match(seeded, settings):
    r = run(seeded, box_image(), ["AMLOR 10 mg", "56 comprimés"], settings)
    top = r["candidates"][0]
    assert top["evidence"]["pack"] == "conflict" and r["status"] != "identified"


def test_substance_only_gives_ambiguous_candidates(seeded, settings):
    r = run(seeded, box_image(), ["AMLODIPINE", "5 mg"], settings)
    assert r["status"] == "ambiguous" and len(r["candidates"]) == 3
    assert {c["dosage"] for c in r["candidates"]} == {"5 MG"}


def test_approximate_name_alone_never_identifies(seeded, settings):
    r = run(seeded, box_image(), ["AMLOX"], settings)
    assert r["status"] != "identified"


def test_barcode_contradicted_by_text(seeded, settings):
    r = run(seeded, box_image(barcode=AMLOR_5_28), ["AMEP", "10 mg"], settings)
    assert r["status"] == "contradictory" and r["reliability"] == "low"


def test_no_match(seeded, settings):
    r = run(seeded, box_image(), ["ZORGLUBINE", "750 mg"], settings)
    assert r["status"] == "not_found" and r["candidates"] == []


def test_unreadable_image(seeded, settings):
    blank = Image.new("RGB", (800, 600), (128, 128, 128))
    buf = io.BytesIO()
    blank.save(buf, "PNG")
    r = run(seeded, buf.getvalue(), [], settings)
    assert r["status"] == "unreadable" and r["reliability"] == "none"


def test_ocr_unavailable(seeded, settings):
    r = run(seeded, box_image(("AMLOR 5 MG",)), None, settings)
    assert r["status"] == "ocr_unavailable" and r["ocr"]["available"] is False
    with_code = run(seeded, box_image(barcode=AMLOR_5_28), None, settings)
    assert with_code["status"] == "identified" and any("OCR indisponible" in w for w in with_code["warnings"])


def test_simulated_medicines_are_excluded_from_real_results(seeded, settings):
    lines = ["DOLIPRANE", "500 MG", "PARACETAMOL", "16 COMPRIMES"]
    r = run(seeded, box_image(), lines, settings)
    assert r["status"] == "not_found" and all(c["data_status"] != "simulated" for c in r["candidates"])
    demo = run(seeded, box_image(), lines, settings, pill_include_simulated=True)
    assert demo["candidates"][0]["data_status"] == "simulated" and any("démonstration" in w for w in demo["warnings"])


# ---------- 14. Fichiers sensibles ----------

def test_images_are_not_stored_and_trace_has_no_ocr_text(seeded, settings):
    r = run(seeded, box_image(barcode=AMLOR_5_28), ["Mme Exemple Patiente", "AMLOR 5 mg"], settings)
    assert r["image"]["stored"] is False and not (settings.data_dir / "raw" / "uploads").exists()
    trace = seeded.scalar(select(m.IdentificationResult).where(m.IdentificationResult.id == r["identification_id"]))
    assert trace.image_stored is False and trace.image_sha256 and trace.expires_at > trace.created_at
    stored_json = str(trace.hints) + str(trace.extracted) + str(trace.candidates)
    assert "Patiente" not in stored_json and "lines" not in str(trace.hints)


def test_optional_storage_drops_exif_gps(seeded, settings):
    src = Image.open(io.BytesIO(box_image(barcode=AMLOR_5_28))).convert("RGB")
    exif = src.getexif()
    exif[0x8825] = {2: (33.0, 35.0, 0.0)}  # bloc GPS
    buf = io.BytesIO()
    src.save(buf, "JPEG", exif=exif)
    r = run(seeded, buf.getvalue(), [], settings, store_uploaded_images=True)
    files = list((settings.data_dir / "raw" / "uploads").glob("*.jpg"))
    assert r["image"]["stored"] is True and len(files) == 1
    assert 0x8825 not in Image.open(files[0]).getexif()


# ---------- Extraction (exemple de l'énoncé : jamais enregistré comme identification) ----------

def test_extraction_of_example_text():
    vocab = Vocabulary(substances={"paracetamol": (1, "PARACETAMOL")})
    ex = extract([("DOLIPRANE", 60), ("500 MG", 40), ("PARACETAMOL", 30), ("16 COMPRIMES", 20)], vocab)
    assert ex.brand_segments[0] == "doliprane" and ex.dosage_text == "500 mg"
    assert ex.substances[0]["name"] == "PARACETAMOL" and (ex.pack_quantity, ex.pack_unit) == (16, "comprime")
    conc = extract([("ZYMAD 80 mg/ml", 50), ("flacon de 10 ml", 20)])
    assert conc.doses[0].is_concentration and conc.doses[0].mg is None and conc.pack_unit == "ml"
    assert extract([("DOLIPRANE 5OO MG", 50)]).doses == []  # jamais « corrigé » en 500 mg


# ---------- API ----------

@pytest.fixture
def client(seeded):
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_api_identify_end_to_end(client, seeded):
    app.dependency_overrides[get_ocr_engine] = lambda: FakeOcr(["AMLOR 5 mg", "28 comprimés"])
    r = client.post("/api/pills/identify", files={"file": ("boite.png", box_image(barcode=AMLOR_5_28), "image/png")})
    assert r.status_code == 200 and r.json()["status"] == "identified"
    assert seeded.scalar(select(func.count()).select_from(m.IdentificationResult)) == 1


def test_api_rejects_bad_uploads(client):
    app.dependency_overrides[get_ocr_engine] = lambda: FakeOcr([])
    r = client.post("/api/pills/identify", files={"file": ("x.jpg", b"pas une image", "image/jpeg")})
    assert r.status_code == 415 and r.json()["error"]["code"] == "unsupported_media_type"
    big = b"\xff\xd8\xff" + b"0" * int(get_settings().max_upload_mb * 1024 * 1024 + 10)
    r = client.post("/api/pills/identify", files={"file": ("big.jpg", big, "image/jpeg")})
    assert r.status_code == 413 and r.json()["error"]["code"] == "file_too_large"
    assert client.post("/api/pills/identify").status_code == 422


def test_health_reports_pill_identifier_capabilities(client):
    pill = client.get("/api/health").json()["modules"]["pill_identifier"]
    assert "zxing-cpp" in pill["barcode_readers"] and "available" in pill["ocr"]


# ---------- Corpus de référence ----------

def test_corpus_import_links_existing_presentations_and_evaluates(seeded, settings, tmp_path):
    from app.vision.corpus import evaluate, import_corpus
    folder = tmp_path / "corpus"
    (folder / "images").mkdir(parents=True)
    (folder / "images" / "amlor.png").write_bytes(box_image(barcode=AMLOR_5_28))
    (folder / "images" / "inconnu.png").write_bytes(box_image(("X",)))
    header = "IMAGE FILE;SPECIALITE;DOSAGE;FORME;PRESENTATION;EAN13;VIEW;LANGUAGES;ORIGIN;LICENSE;ATTRIBUTION;CAPTURED AT;TRANSCRIPTION;NOTES"
    rows = [f"images/amlor.png;AMLOR;5 MG;COMPRIME;BOITE DE 28;{AMLOR_5_28};back;fr|ar;team_photo;CC BY 4.0;Équipe;2026-10-27T10:00:00;AMLOR | 5 mg | 28 comprimés;",
            "images/amlor.png;AMLOR;5 MG;COMPRIME;BOITE DE 28;;front;fr;team_photo;;Équipe;;;sans licence",
            "images/inconnu.png;INCONNU;1 MG;COMPRIME;BOITE DE 1;;front;fr;team_photo;CC BY 4.0;Équipe;;;"]
    manifest = folder / "manifest.csv"
    manifest.write_text("\n".join([header, *rows]), encoding="utf-8")
    cfg = settings.model_copy(update={"data_dir": tmp_path})
    report = import_corpus(seeded, manifest, cfg)
    assert report["inserted"] == 1 and report["rejected"] == 2
    img = seeded.scalar(select(m.MedicineImage))
    pres = seeded.get(m.MedicinePresentation, img.presentation_id)
    assert pres.ean13 == AMLOR_5_28 and img.view == "back" and img.packaging_languages == ["fr", "ar"]
    assert img.metadata_json["quality"]["usable"] and img.annotations[0].value == "AMLOR\n5 mg\n28 comprimés"
    assert import_corpus(seeded, manifest, cfg)["inserted"] == 0  # idempotent
    result = evaluate(seeded, cfg, FakeOcr(["AMLOR", "5 mg", "28 comprimés"]))
    assert result["evaluated"] == 1 and result["identified_correctly_rate"] == 1.0 and result["barcode_read_rate"] == 1.0
    assert seeded.scalar(select(func.count()).select_from(m.IdentificationResult)) == 0  # aucune trace
