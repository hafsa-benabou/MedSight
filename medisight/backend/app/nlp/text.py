"""Normalisation multilingue (français, arabe, darija en alphabet arabe ou latin « arabizi »)."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_AR_DIACRITICS = re.compile("[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]")
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "0123456789" * 2)
_UNITS = r"mg|mgr|g|gr|ml|mcg|µg|μg|ug|ui|%|mmol|cp|ملغ|مغ|ملغرام|غرام|غ|مل"
# « 500mg » -> « 500 mg » sans casser l'arabizi (« ch7al », « 3afak »)
_UNIT_GLUE = re.compile(rf"(?<![\w.])(\d+(?:\.\d+)?)({_UNITS})(?![^\W\d_])")
_ARABIC = re.compile(r"[\u0600-\u06ff]")
_LATIN = re.compile(r"[a-z]")


def normalize_arabic(s: str) -> str:
    s = _AR_DIACRITICS.sub("", s).replace("\u0640", "")
    s = re.sub("[إأآٱ]", "ا", s)
    return s.replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")


def normalize_text(text: object) -> str:
    """Minuscules, sans accents, chiffres arabes -> latins, ponctuation retirée, unités détachées."""
    if text is None:
        return ""
    s = unicodedata.normalize("NFKC", str(text)).translate(_DIGITS).lower()
    s = normalize_arabic(s)
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    s = s.replace("œ", "oe").replace("æ", "ae")
    s = re.sub(r"(?<=\d)[,٫](?=\d)", ".", s)
    s = re.sub(r"[’'`´]", " ", s)
    s = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", s)
    s = re.sub(r"[^\w\s%/+.\-]", " ", s).replace("_", " ")
    s = re.sub(r"(?<!\w)-|-(?!\w)", " ", s)
    s = _UNIT_GLUE.sub(r"\1 \2", s)
    s = re.sub(r"\s*/\s*", " / ", s)
    return re.sub(r"\s+", " ", s).strip()


@dataclass(frozen=True)
class Token:
    text: str
    start: int
    end: int
    index: int


def tokenize(norm: str) -> list[Token]:
    return [Token(m.group(), m.start(), m.end(), i) for i, m in enumerate(re.finditer(r"\S+", norm))]


def has_arabic(s: str) -> bool:
    return bool(_ARABIC.search(s))


def has_latin(s: str) -> bool:
    return bool(_LATIN.search(s))


def is_number(s: str) -> bool:
    return bool(re.fullmatch(r"\d+(?:\.\d+)?", s))


_AR_PREFIXES = ("وال", "فال", "بال", "كال", "لل", "ال", "و", "ف", "ب", "ل", "ك")


def arabic_variants(token: str) -> list[str]:
    """Variantes sans proclitiques : « فكازا » -> « كازا », « بالرباط » -> « رباط »."""
    out = [token]
    for p in _AR_PREFIXES:
        if token.startswith(p) and len(token) - len(p) >= 3:
            out.append(token[len(p):])
    return list(dict.fromkeys(out))


_AR2LAT = {"ب": "b", "پ": "b", "ت": "t", "ث": "t", "ج": "g", "خ": "k", "د": "d", "ذ": "d", "ر": "r", "ز": "s",
           "س": "s", "ش": "s", "ص": "s", "ض": "d", "ط": "t", "ظ": "d", "غ": "g", "ف": "f", "ڤ": "f", "ق": "k",
           "ك": "k", "ڭ": "g", "گ": "g", "ل": "l", "م": "m", "ن": "n"}


def skeleton_latin(word: str) -> str:
    """Squelette consonantique approximatif (« doliprane » -> « dlbrn ») pour rapprocher les écritures."""
    w = re.sub(r"[^a-z]", "", normalize_text(word))
    for a, b in (("ph", "f"), ("ch", "s"), ("sh", "s"), ("qu", "k"), ("ck", "k"), ("kh", "k"), ("gh", "g"), ("th", "t")):
        w = w.replace(a, b)
    w = re.sub(r"c(?=[eiy])", "s", w)
    w = w.translate(str.maketrans({"c": "k", "q": "k", "p": "b", "v": "f", "z": "s", "j": "g", "w": "", "h": ""}))
    w = w.replace("x", "ks")
    w = re.sub("[aeiouy]", "", w)
    return re.sub(r"(.)\1+", r"\1", w)


def skeleton_arabic(word: str) -> str:
    """Squelette consonantique d'un mot en alphabet arabe (« دوليبران » -> « dlbrn »)."""
    w = "".join(_AR2LAT.get(ch, "") for ch in normalize_arabic(word))
    return re.sub(r"(.)\1+", r"\1", w)
