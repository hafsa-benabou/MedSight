"""Détection de langue : français, arabe standard, darija (alphabet arabe ou latin « arabizi »), anglais.

Heuristique à base de lexiques : un message court (« ch7al doliprane ? ») ne laisse pas assez de texte à un
modèle statistique. Le résultat sert à choisir la langue de réponse, jamais à filtrer les données."""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.nlp.text import has_arabic, normalize_text

# Mots fréquents propres à la darija marocaine écrite en alphabet arabe (après normalize_text)
DARIJA_AR = {"شنو", "شنهو", "اشنو", "شحال", "بشحال", "واش", "فين", "كاين", "كاينه", "ديال", "ديالو", "ديالها", "هاد", "هادا",
             "هادي", "بغيت", "عافاك", "دابا", "علاش", "كيفاش", "مزيان", "خاصني", "نلقى", "نقلب", "صيدليه", "الدوا", "دوا",
             "تمن", "التمن", "غالي", "رخيص", "شي", "ماشي", "حتى", "كنقلب", "واخا", "بزاف", "قداش", "ولا", "نشري"}
# Arabizi : chiffres utilisés comme lettres (3, 7, 9, 2) et mots darija latins
_ARABIZI_DIGIT = re.compile(r"[a-z][2379]|[2379][a-z]")
DARIJA_LAT = {"ch7al", "chhal", "chehal", "ch7al", "bch7al", "bchhal", "wach", "wash", "fin", "fen", "kayn", "kayen", "kaina",
              "dyal", "dial", "dyalo", "had", "hada", "hadi", "bghit", "bghit", "3afak", "afak", "daba", "3lach", "kifach",
              "mzyan", "khasni", "n9leb", "nl9a", "nlqa", "taman", "tamane", "taman", "ghali", "rkhis", "chi", "machi",
              "dwa", "dawa", "sbitar", "saydaliya", "saydlia", "farmasyan", "fermasyan", "bzaf", "9adach", "ola", "wla",
              "chno", "chnou", "achno", "ach", "smito", "katdir", "kaydir", "kandir", "ndir", "nchri", "nakhod", "nakhdo",
              "wa7ed", "wa7da", "mra", "rasi", "kerchi", "brd", "l3ayalat", "drari", "mo3a", "m3a", "lih", "liha", "ana"}
FRENCH = {"le", "la", "les", "de", "du", "des", "un", "une", "est", "quel", "quelle", "quels", "quelles", "prix", "combien",
          "je", "cherche", "pour", "pharmacie", "médicament", "medicament", "sont", "et", "avec", "sans", "dans", "ou",
          "bonjour", "merci", "coute", "substance", "active", "generique", "generiques", "dosage", "dosages", "qu", "est-ce",
          "donne", "moi", "pouvez", "vous", "peux", "tu", "a", "au", "aux", "sur", "il", "elle", "y"}
ENGLISH = {"the", "what", "is", "price", "how", "much", "of", "where", "find", "pharmacy", "drug", "medicine", "generic",
           "active", "ingredient", "hello", "hi", "thanks", "does", "cost", "which", "are"}


@dataclass(frozen=True)
class LanguageGuess:
    code: str  # fr | ar | darija | darija_latin | en
    script: str  # latin | arabic | mixed
    reply_language: str  # fr | ar  (les réponses darija latines sont rédigées en français, plus lisible)
    confidence: float

    def summary(self) -> dict:
        return {"code": self.code, "script": self.script, "reply_language": self.reply_language,
                "confidence": round(self.confidence, 2)}


def detect_language(message: str) -> LanguageGuess:
    raw = message or ""
    norm = normalize_text(raw)
    tokens = norm.split()
    if not tokens:
        return LanguageGuess("fr", "latin", "fr", 0.0)
    arabic_tokens = [t for t in tokens if has_arabic(t)]
    latin_tokens = [t for t in tokens if re.search(r"[a-z]", t)]
    script = "arabic" if arabic_tokens and not latin_tokens else "latin" if not arabic_tokens else "mixed"
    if len(arabic_tokens) >= max(1, len(latin_tokens)):
        darija = sum(t in DARIJA_AR or any(t.endswith(w) for w in ("ديال", "شحال")) for t in arabic_tokens)
        conf = min(1.0, 0.55 + 0.15 * darija)
        return LanguageGuess("darija" if darija else "ar", script, "ar", conf)
    darija = sum(t in DARIJA_LAT for t in latin_tokens) + sum(bool(_ARABIZI_DIGIT.search(t)) for t in latin_tokens)
    french = sum(t in FRENCH for t in latin_tokens)
    english = sum(t in ENGLISH for t in latin_tokens)
    if darija and darija >= french:
        return LanguageGuess("darija_latin", script, "fr", min(1.0, 0.5 + 0.15 * darija))
    if english > french:
        return LanguageGuess("en", script, "fr", min(1.0, 0.4 + 0.1 * english))
    return LanguageGuess("fr", script, "fr", min(1.0, 0.45 + 0.1 * french))
