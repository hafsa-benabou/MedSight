"""Intégration avec le VRAI Tesseract (aucun OCR simulé) sur des images de boîte rendues par ordinateur.

Ignorés (skipped) si Tesseract ou ses modèles ne sont pas installés. Ces images sont propres et synthétiques :
réussir ces tests ne valide PAS la reconnaissance sur des photos réelles (voir `cli evaluate-identifier`)."""
import io
from pathlib import Path

import numpy as np
import pytest
import zxingcpp
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from rapidfuzz import fuzz

from app.core.config import get_settings
from app.nlp.text import normalize_text
from app.vision.identify import identify_image
from app.vision.ocr import TesseractEngine

ENGINE = TesseractEngine(get_settings())
STATUS = ENGINE.status()
pytestmark = pytest.mark.skipif(not STATUS.get("available"), reason=f"Tesseract indisponible : {STATUS.get('reason')}")
FONT_DIRS = ("/usr/share/fonts", "C:/Windows/Fonts")


def _font(names: tuple[str, ...], size: int):
    for d in FONT_DIRS:
        for name in names:
            hits = list(Path(d).rglob(name)) if Path(d).exists() else []
            if hits:
                return ImageFont.truetype(str(hits[0]), size)
    return None


LATIN = _font(("DejaVuSans-Bold.ttf", "arialbd.ttf"), 80)
SMALL = _font(("DejaVuSans.ttf", "arial.ttf"), 48)
ARABIC = _font(("NotoNaskhArabic-Regular.ttf", "NotoSansArabic-Regular.ttf", "DejaVuSans.ttf", "arial.ttf"), 72)


def render(lines, *, rotate=0, blur=0.0, noise=0, barcode=None) -> bytes:
    if LATIN is None:
        pytest.skip("Aucune police TrueType disponible pour rendre l'image")
    img = Image.new("RGB", (1400, 1000), (250, 248, 240))
    draw = ImageDraw.Draw(img)
    y = 80
    for text, big in lines:
        draw.text((80, y), text, fill=(20, 30, 90), font=LATIN if big else SMALL)
        y += 130 if big else 80
    if barcode:
        bc = Image.fromarray(np.array(zxingcpp.create_barcode(barcode, zxingcpp.BarcodeFormat.EAN13).to_image(scale=4)))
        img.paste(bc.convert("RGB"), (80, 1000 - bc.height - 60))
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    if noise:
        arr = np.asarray(img).astype(np.int16) + np.random.default_rng(0).integers(-noise, noise, (1000, 1400, 3))
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    if rotate:
        img = img.rotate(rotate, expand=True, fillcolor=(250, 248, 240))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return buf.getvalue()


BOX = [("AMLOR", True), ("5 mg", True), ("Amlodipine", False), ("28 comprimés", False)]


def test_tesseract_reports_languages():
    assert {"fra", "eng"} <= set(STATUS["installed_languages"])
    assert STATUS["version"]


def test_real_ocr_identifies_rendered_box(seeded):
    r = identify_image(seeded, render(BOX), get_settings(), ENGINE)
    assert r["ocr"]["engine"] == "tesseract" and r["ocr"]["lines"]
    assert r["status"] == "identified", (r["status"], r["ocr"]["lines"], r["reasons"])
    top = r["candidates"][0]
    assert (top["brand"], top["dosage"], top["presentation"]) == ("AMLOR", "5 MG", "BOITE DE 28")
    assert top["evidence"]["dosage"] == "match" and top["evidence"]["pack"] == "match"


def test_real_ocr_on_noisy_slightly_blurred_box(seeded):
    r = identify_image(seeded, render(BOX, blur=1.2, noise=25), get_settings(), ENGINE)
    assert r["status"] == "identified", (r["status"], r["ocr"]["lines"])


def test_real_ocr_recovers_rotated_box(seeded):
    r = identify_image(seeded, render(BOX, rotate=90), get_settings(), ENGINE)
    assert r["ocr"]["rotation"] in (90, 270) and r["status"] == "identified", (r["ocr"]["passes"], r["ocr"]["lines"])


def test_real_ocr_and_barcode_agree(seeded):
    r = identify_image(seeded, render(BOX, barcode="6118000480020"), get_settings(), ENGINE)
    assert r["status"] == "identified" and r["reliability"] == "high"
    assert r["candidates"][0]["evidence"]["barcode"] == "match"


@pytest.mark.skipif("ara" not in STATUS.get("installed_languages", []), reason="modèle ara absent")
def test_real_ocr_reads_arabic_text():
    if ARABIC is None:
        pytest.skip("Aucune police arabe disponible")
    img = Image.new("RGB", (1400, 500), "white")
    draw = ImageDraw.Draw(img)
    text = "أقراص مغلفة"  # « comprimés pelliculés »
    try:
        draw.text((1300, 150), text, fill="black", font=ARABIC, anchor="ra", direction="rtl")
    except (KeyError, ValueError, OSError):
        pytest.skip("Rendu arabe (libraqm) indisponible pour Pillow")
    result = ENGINE.read(np.asarray(img.convert("L")))
    read = normalize_text(" ".join(w.text for w in result.words))
    assert fuzz.partial_ratio(normalize_text(text), read) >= 70, read
