"""Villes marocaines et leurs variantes d'écriture (français, darija latin, arabe)."""
from __future__ import annotations

from app.nlp.text import normalize_text

CITY_ALIASES: dict[str, list[str]] = {
    "Casablanca": ["casablanca", "casa", "dar beida", "dar lbida", "dar el beida", "darbeida", "الدار البيضاء", "كازا", "كازابلانكا", "البيضاء"],
    "Rabat": ["rabat", "rbat", "الرباط"],
    "Salé": ["sale", "sla", "سلا"],
    "Témara": ["temara", "tmara", "تمارة"],
    "Marrakech": ["marrakech", "marrakesh", "marrakch", "mrakch", "mrrakch", "مراكش"],
    "Tanger": ["tanger", "tangier", "tanja", "طنجة"],
    "Fès": ["fes", "fez", "فاس"],
    "Meknès": ["meknes", "mknes", "مكناس"],
    "Agadir": ["agadir", "أكادير", "اكادير"],
    "Oujda": ["oujda", "wjda", "وجدة"],
    "Kénitra": ["kenitra", "qnitra", "القنيطرة"],
    "Tétouan": ["tetouan", "tetuan", "تطوان"],
    "Mohammedia": ["mohammedia", "mohamedia", "المحمدية"],
    "El Jadida": ["el jadida", "eljadida", "الجديدة"],
    "Safi": ["safi", "asfi", "آسفي", "اسفي"],
    "Béni Mellal": ["beni mellal", "benimellal", "بني ملال"],
    "Nador": ["nador", "الناظور"],
    "Laâyoune": ["laayoune", "layoune", "العيون"],
    "Khouribga": ["khouribga", "خريبكة"],
    "Settat": ["settat", "سطات"],
    "Berrechid": ["berrechid", "برشيد"],
    "Essaouira": ["essaouira", "swira", "الصويرة"],
    "Ouarzazate": ["ouarzazate", "ورزازات"],
    "Errachidia": ["errachidia", "الرشيدية"],
    "Larache": ["larache", "العرائش"],
    "Dakhla": ["dakhla", "الداخلة"],
    "Al Hoceïma": ["al hoceima", "hoceima", "الحسيمة"],
    "Ifrane": ["ifrane", "إفران"],
    "Tiznit": ["tiznit", "تيزنيت"],
}

CITY_LOOKUP: dict[str, str] = {}
for _canonical, _aliases in CITY_ALIASES.items():
    for _alias in [_canonical, *_aliases]:
        CITY_LOOKUP[normalize_text(_alias)] = _canonical


def canonical_city(raw: str | None) -> tuple[str | None, str | None]:
    """Retourne (clé normalisée, nom affiché) : « CASA » -> (« casablanca », « Casablanca »)."""
    key = normalize_text(raw or "")
    if not key:
        return None, None
    display = CITY_LOOKUP.get(key)
    if display:
        return normalize_text(display), display
    return key, str(raw).strip().title()
