"""Validation des codes EAN-13 (codes-barres des boîtes, préfixe GS1 Maroc 611) et des GTIN-14.

Un GTIN-14 commençant par « 0 » est l'EAN-13 de la boîte précédé d'un zéro (forme lue dans les DataMatrix) :
il est ramené à l'EAN-13. Un GTIN-14 d'indicateur 1 à 8 désigne un conditionnement logistique (carton, colis),
pas la boîte remise au patient : il est conservé avec le statut « gtin14 » mais jamais utilisé comme EAN-13."""
from __future__ import annotations

import re


def gtin_check_digit_ok(code: str) -> bool:
    """Clé de contrôle GS1 (EAN-8, EAN-13, GTIN-14) : poids 3 et 1 en partant de la droite, hors clé."""
    if not code or not code.isdigit() or len(code) < 8:
        return False
    digits = [int(c) for c in code]
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(digits[:-1])))
    return (10 - total % 10) % 10 == digits[-1]


def ean13_is_valid(code: str) -> bool:
    return bool(code) and len(code) == 13 and gtin_check_digit_ok(code)


def normalize_ean(raw: object) -> tuple[str | None, str]:
    """Retourne (code, statut) avec statut parmi valid, invalid_checksum, gtin14, not_ean13, missing."""
    if raw is None:
        return None, "missing"
    if isinstance(raw, (int, float)):
        text = str(int(raw))
    else:
        text = re.sub(r"\D", "", str(raw).strip())
    if not text:
        return None, "missing"
    if len(text) == 13:
        return text, "valid" if ean13_is_valid(text) else "invalid_checksum"
    if len(text) == 14:
        if not gtin_check_digit_ok(text):
            return text, "invalid_checksum"
        if text.startswith("0"):
            return text[1:], "valid"  # GTIN-14 = « 0 » + EAN-13
        return text, "gtin14"
    return text, "not_ean13"
