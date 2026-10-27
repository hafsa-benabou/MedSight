"""Lecture des codes-barres des boîtes : EAN-13 (linéaire), ITF-14 / GTIN-14, DataMatrix GS1 (sérialisation).

Lecteur principal : zxing-cpp (local, sans service externe) ; secours : cv2.barcode (EAN/UPC seulement).
Chaque code est validé par app.core.ean.normalize_ean : un code dont la clé est fausse est signalé et jamais
« corrigé » en un code voisin. Un DataMatrix GS1 fournit le GTIN (AI 01) et, s'ils sont présents, la date de
péremption (AI 17), le lot (AI 10) et le numéro de série (AI 21, non renvoyé : identifiant unique de la boîte)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import cv2
import numpy as np

from app.core.ean import normalize_ean

_GS = "\x1d"
_FIXED_AI = {"01": 14, "17": 6, "11": 6, "15": 6}
_VARIABLE_AI = ("10", "21")


@dataclass
class BarcodeRead:
    format: str
    raw: str
    code: str | None
    status: str  # valid | invalid_checksum | gtin14 | not_ean13 | missing | unsupported
    reader: str
    gs1: dict[str, str] = field(default_factory=dict)

    def summary(self) -> dict:
        out = {"format": self.format, "code": self.code, "status": self.status, "reader": self.reader}
        if "17" in self.gs1:
            out["expiry"] = self.gs1["17"]
        if "10" in self.gs1:
            out["lot"] = self.gs1["10"]
        return out


def parse_gs1(text: str) -> dict[str, str]:
    """Éléments GS1 d'un DataMatrix : forme lisible « (01)…(17)… » ou brute (séparateur FNC1 = GS)."""
    text = text.strip()
    if text.startswith("]d2") or text.startswith("]C1"):
        text = text[3:]
    if "(" in text:
        return {ai: value for ai, value in re.findall(r"\((\d{2,4})\)([^(]*)", text)}
    out: dict[str, str] = {}
    i = 0
    text = text.lstrip(_GS)
    while i < len(text) - 1:
        if text[i] == _GS:  # séparateur FNC1 après un champ de longueur variable
            i += 1
            continue
        ai = text[i:i + 2]
        if ai in _FIXED_AI:
            n = _FIXED_AI[ai]
            out[ai] = text[i + 2:i + 2 + n]
            i += 2 + n
        elif ai in _VARIABLE_AI:
            end = text.find(_GS, i + 2)
            end = len(text) if end < 0 else end
            out[ai] = text[i + 2:end]
            i = end + 1
        else:
            break  # identifiant non géré : on s'arrête plutôt que de deviner la suite
    return out


def _interpret(fmt: str, text: str, reader: str) -> BarcodeRead:
    if fmt in ("DataMatrix", "QRCode", "Code128"):
        gs1 = parse_gs1(text)
        if "01" in gs1:
            code, status = normalize_ean(gs1["01"])
            return BarcodeRead(fmt, text, code, status, reader, gs1)
        return BarcodeRead(fmt, text, None, "unsupported", reader)
    code, status = normalize_ean(text)
    return BarcodeRead(fmt, text, code, status, reader)


def _read_zxing(gray: np.ndarray) -> list[BarcodeRead]:
    import zxingcpp
    formats = (zxingcpp.BarcodeFormat.EAN13 | zxingcpp.BarcodeFormat.EAN8 | zxingcpp.BarcodeFormat.UPCA
               | zxingcpp.BarcodeFormat.ITF | zxingcpp.BarcodeFormat.DataMatrix | zxingcpp.BarcodeFormat.Code128)
    out = []
    for r in zxingcpp.read_barcodes(gray, formats=formats, try_rotate=True, try_downscale=True):
        if r.valid:
            out.append(_interpret(r.format.name, r.text, "zxing-cpp"))
    return out


def _read_opencv(gray: np.ndarray) -> list[BarcodeRead]:
    detector = cv2.barcode.BarcodeDetector()
    ok, infos, types, _ = detector.detectAndDecodeWithType(gray)
    if not ok:
        return []
    return [_interpret(str(t), info, "opencv") for info, t in zip(infos, types) if info]


def available_readers() -> list[str]:
    readers = []
    try:
        import zxingcpp  # noqa: F401
        readers.append("zxing-cpp")
    except ImportError:
        pass
    if hasattr(cv2, "barcode"):
        readers.append("opencv")
    return readers


def read_barcodes(bgr: np.ndarray) -> list[BarcodeRead]:
    gray = bgr if bgr.ndim == 2 else cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    readers = available_readers()
    attempts = [gray]
    if max(gray.shape[:2]) < 1000:  # petits codes : agrandissement
        attempts.append(cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC))
    found: dict[tuple[str, str], BarcodeRead] = {}
    for img in attempts:
        for reader in readers:
            reads = _read_zxing(img) if reader == "zxing-cpp" else _read_opencv(img)
            for b in reads:
                # même symbole lu par deux lecteurs : une entrée ; un EAN-13 et un DataMatrix du même GTIN : deux
                family = "matrix" if b.format in ("DataMatrix", "QRCode") else "linear"
                found.setdefault((family, b.code or b.raw), b)
        if found:
            break
    return list(found.values())
