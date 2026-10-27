"""Prétraitement OpenCV : contrôle de qualité, zones de texte probables, variantes d'image pour l'OCR.

Aucune transformation n'est supposée meilleure a priori : l'orchestrateur passe plusieurs variantes à l'OCR et garde
celle dont la lecture est la plus confiante (voir identify.py). Les seuils de qualité sont des heuristiques initiales,
à recalibrer sur le corpus de photos réelles (docs/PILL_IDENTIFIER.md)."""
from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

import cv2
import numpy as np

SHARPNESS_UNUSABLE = 12.0  # variance du laplacien (image ramenée à 1000 px) : en dessous, photo trop floue
SHARPNESS_WARNING = 60.0
CONTRAST_UNUSABLE = 8.0  # écart-type des niveaux de gris
DARK, BRIGHT = 35.0, 225.0
REFERENCE_SIDE = 1000


@dataclass
class Quality:
    width: int
    height: int
    sharpness: float
    brightness: float
    contrast: float
    text_regions: int
    usable: bool
    issues: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {"width": self.width, "height": self.height, "sharpness": round(self.sharpness, 1),
                "brightness": round(self.brightness, 1), "contrast": round(self.contrast, 1),
                "text_regions": self.text_regions, "usable": self.usable, "issues": self.issues}


def to_gray(bgr: np.ndarray) -> np.ndarray:
    return bgr if bgr.ndim == 2 else cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)


def resize_max(img: np.ndarray, side: int) -> np.ndarray:
    h, w = img.shape[:2]
    scale = side / max(h, w)
    if scale >= 1:
        return img
    return cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)


def text_regions(gray: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Zones susceptibles de contenir du texte (gradient morphologique + fermeture horizontale), en pixels."""
    small = resize_max(gray, REFERENCE_SIDE)
    ratio = gray.shape[1] / small.shape[1]
    grad = cv2.morphologyEx(small, cv2.MORPH_GRADIENT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    _, bw = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    closed = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (9, 1)))
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if h < 6 or w < 12 or w < h * 1.2 or h > small.shape[0] * 0.5:
            continue
        fill = cv2.countNonZero(closed[y:y + h, x:x + w]) / float(w * h)
        if fill >= 0.35:
            boxes.append(tuple(int(round(v * ratio)) for v in (x, y, w, h)))
    return sorted(boxes, key=lambda b: (b[1], b[0]))


def assess_quality(bgr: np.ndarray, min_side: int) -> Quality:
    gray = to_gray(bgr)
    h, w = gray.shape[:2]
    small = resize_max(gray, REFERENCE_SIDE)
    sharpness = float(cv2.Laplacian(small, cv2.CV_64F).var())
    brightness, contrast = float(small.mean()), float(small.std())
    regions = len(text_regions(gray))
    issues, usable = [], True
    if min(h, w) < min_side:
        issues.append("resolution_insuffisante")
        usable = False
    if sharpness < SHARPNESS_UNUSABLE:
        issues.append("image_tres_floue")
        usable = False
    elif sharpness < SHARPNESS_WARNING:
        issues.append("image_peu_nette")
    if contrast < CONTRAST_UNUSABLE:
        issues.append("contraste_insuffisant")
        usable = False
    if brightness < DARK:
        issues.append("image_sombre")
    elif brightness > BRIGHT:
        issues.append("image_surexposee")
    if regions == 0:
        issues.append("aucune_zone_de_texte_detectee")
    return Quality(w, h, sharpness, brightness, contrast, regions, usable, issues)


def _upscale_small(gray: np.ndarray) -> np.ndarray:
    # Tesseract lit mal les caractères de moins de ~20 px : agrandissement des petites photos
    if max(gray.shape[:2]) < 1200:
        return cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    return gray


def variants(bgr: np.ndarray) -> Iterator[tuple[str, np.ndarray]]:
    """Variantes à comparer, de la plus neutre à la plus transformée (générées à la demande)."""
    gray = _upscale_small(to_gray(bgr))
    steps: list[tuple[str, Callable[[], np.ndarray]]] = [
        ("gray", lambda: gray),
        ("clahe", lambda: cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)),
        ("denoise_otsu", lambda: cv2.threshold(cv2.medianBlur(gray, 3), 0, 255,
                                               cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]),
        ("adaptive", lambda: cv2.adaptiveThreshold(cv2.GaussianBlur(gray, (3, 3), 0), 255,
                                                   cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)),
    ]
    if gray.mean() < 110:  # texte clair sur fond sombre
        steps.append(("inverted", lambda: 255 - gray))
    for name, make in steps:
        yield name, make()


_ROTATIONS = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}


def rotate(img: np.ndarray, angle: int) -> np.ndarray:
    """Rotation par quart de tour (boîte photographiée de côté ou à l'envers)."""
    return cv2.rotate(img, _ROTATIONS[angle]) if angle in _ROTATIONS else img
