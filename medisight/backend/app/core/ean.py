"""Validation des codes EAN-13 (codes-barres des boîtes, préfixe GS1 Maroc 611)."""
from __future__ import annotations

import re


def ean13_is_valid(code: str) -> bool:
    if not code or len(code) != 13 or not code.isdigit():
        return False
    digits = [int(c) for c in code]
    total = sum(d * (3 if i % 2 else 1) for i, d in enumerate(digits[:12]))
    return (10 - total % 10) % 10 == digits[12]


def normalize_ean(raw: object) -> tuple[str | None, str]:
    """Retourne (code, statut) avec statut parmi valid, invalid_checksum, not_ean13, missing."""
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
    return text, "not_ean13"
