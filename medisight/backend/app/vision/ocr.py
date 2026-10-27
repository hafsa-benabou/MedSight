"""OCR multilingue (Tesseract via pytesseract) : mots, lignes, coordonnées et scores de confiance.

Le moteur est vérifié au démarrage de chaque analyse : binaire présent, version, langues installées (fra, ara, eng).
Une langue absente est retirée avec un avertissement ; sans français ni anglais, l'OCR est déclaré indisponible.
Les images ne quittent jamais la machine : Tesseract tourne en local."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Protocol

import numpy as np

from app.core.config import Settings, get_settings


class OcrUnavailable(RuntimeError):
    """Tesseract absent, mal configuré ou sans modèle de langue utilisable."""


@dataclass
class OcrWord:
    text: str
    confidence: float  # 0-100, tel que fourni par Tesseract
    bbox: tuple[int, int, int, int]  # x, y, largeur, hauteur (pixels de l'image analysée)
    line_key: tuple[int, int, int]


@dataclass
class OcrLine:
    text: str
    confidence: float
    bbox: tuple[int, int, int, int]

    @property
    def height(self) -> int:
        return self.bbox[3]


@dataclass
class OcrResult:
    words: list[OcrWord]
    lines: list[OcrLine]
    engine: str
    languages: str
    variant: str = ""
    rotation: int = 0
    elapsed_ms: float = 0.0
    warnings: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

    @property
    def mean_confidence(self) -> float:
        confs = [w.confidence for w in self.words if w.confidence >= 0]
        return sum(confs) / len(confs) if confs else 0.0

    @property
    def score(self) -> float:
        """Critère de choix entre variantes : caractères alphanumériques lus avec une confiance >= 60, pondérés."""
        return sum(w.confidence / 100 * sum(c.isalnum() for c in w.text)
                   for w in self.words if w.confidence >= 60 and sum(c.isalnum() for c in w.text) >= 2)


class OcrEngine(Protocol):
    name: str

    def status(self) -> dict: ...

    def read(self, image: np.ndarray) -> OcrResult: ...


def group_lines(words: list[OcrWord]) -> list[OcrLine]:
    by_line: dict[tuple[int, int, int], list[OcrWord]] = {}
    for w in words:
        by_line.setdefault(w.line_key, []).append(w)
    lines = []
    for ws in by_line.values():
        ws.sort(key=lambda w: w.bbox[0])
        x0, y0 = min(w.bbox[0] for w in ws), min(w.bbox[1] for w in ws)
        x1 = max(w.bbox[0] + w.bbox[2] for w in ws)
        y1 = max(w.bbox[1] + w.bbox[3] for w in ws)
        lines.append(OcrLine(" ".join(w.text for w in ws), sum(w.confidence for w in ws) / len(ws), (x0, y0, x1 - x0, y1 - y0)))
    return sorted(lines, key=lambda line: (line.bbox[1], line.bbox[0]))


class TesseractEngine:
    name = "tesseract"
    WANTED = ("fra", "ara", "eng")

    def __init__(self, settings: Settings):
        self.settings = settings
        self._status: dict | None = None

    def status(self) -> dict:
        if self._status is None:
            self._status = self._probe()
        return self._status

    def _probe(self) -> dict:
        try:
            import pytesseract
        except ImportError:
            return {"available": False, "engine": self.name, "reason": "pytesseract non installé"}
        if self.settings.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self.settings.tesseract_cmd
        try:
            version = str(pytesseract.get_tesseract_version())
            installed = set(pytesseract.get_languages(config=""))
        except Exception as exc:  # TesseractNotFoundError, PermissionError…
            return {"available": False, "engine": self.name,
                    "reason": f"Tesseract introuvable ou inutilisable ({type(exc).__name__})"}
        requested = [lang for lang in self.settings.tesseract_langs.split("+") if lang]
        usable = [lang for lang in requested if lang in installed]
        missing = [lang for lang in requested if lang not in installed]
        status = {"available": bool({"fra", "eng"} & set(usable)), "engine": self.name, "version": version,
                  "languages": "+".join(usable), "missing_languages": missing,
                  "installed_languages": sorted(installed & set(self.WANTED))}
        if not status["available"]:
            status["reason"] = "Aucun modèle de langue fra ou eng installé"
        return status

    def read(self, image: np.ndarray) -> OcrResult:
        st = self.status()
        if not st["available"]:
            raise OcrUnavailable(st.get("reason", "OCR indisponible"))
        import pytesseract
        start = time.perf_counter()
        try:
            # psm 11 : texte épars (une boîte comporte des blocs dispersés, de tailles et d'orientations variées)
            data = pytesseract.image_to_data(image, lang=st["languages"], config="--oem 1 --psm 11",
                                             output_type=pytesseract.Output.DICT,
                                             timeout=self.settings.ocr_timeout_seconds)
        except RuntimeError as exc:  # délai dépassé
            raise OcrUnavailable(f"OCR interrompu : {exc}") from exc
        except pytesseract.TesseractError as exc:
            raise OcrUnavailable(f"Erreur Tesseract : {str(exc)[:200]}") from exc
        words = []
        for i, raw in enumerate(data["text"]):
            text = (raw or "").strip()
            conf = float(data["conf"][i])
            if not text or conf < 0:
                continue
            words.append(OcrWord(text, conf, (int(data["left"][i]), int(data["top"][i]), int(data["width"][i]),
                                              int(data["height"][i])),
                                 (int(data["block_num"][i]), int(data["par_num"][i]), int(data["line_num"][i]))))
        warnings = [f"Modèle de langue absent : {lang}" for lang in st["missing_languages"]]
        return OcrResult(words, group_lines(words), self.name, st["languages"],
                         elapsed_ms=(time.perf_counter() - start) * 1000, warnings=warnings)


class DisabledEngine:
    name = "none"

    def status(self) -> dict:
        return {"available": False, "engine": self.name, "reason": "OCR désactivé (OCR_ENGINE=none)"}

    def read(self, image: np.ndarray) -> OcrResult:
        raise OcrUnavailable("OCR désactivé (OCR_ENGINE=none)")


@lru_cache
def default_engine() -> OcrEngine:
    settings = get_settings()
    return TesseractEngine(settings) if settings.ocr_engine == "tesseract" else DisabledEngine()
