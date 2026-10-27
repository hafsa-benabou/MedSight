"""Détection d'intention par lexiques multilingues (français, arabe, darija arabe et latine, anglais).

Chaque intention possède des expressions déclencheuses ; un message est comparé après normalisation
(normalize_text), avec tolérance aux fautes pour les mots longs. Les intentions de sécurité (urgence, posologie,
avis médical) sont prioritaires : elles ne doivent jamais être masquées par une question de prix."""
from __future__ import annotations

from dataclasses import dataclass, field

from rapidfuzz import fuzz

from app.nlp.text import arabic_variants, has_arabic, normalize_text

# Ordre = priorité en cas d'égalité de score
INTENT_PATTERNS: dict[str, list[str]] = {
    "emergency": ["surdose", "overdose", "intoxication", "empoisonnement", "empoisonne", "j ai avale", "a avale",
                  "trop de comprimes", "suicide", "me tuer", "inconscient", "convulsion", "ne respire plus",
                  "تسمم", "انتحار", "بلع", "بلعت", "شرب الدوا كامل", "tsmem", "tsemem", "bla3", "bl3at", "bla3t"],
    "posology": ["posologie", "combien de comprimes", "combien de comprime", "combien par jour", "fois par jour",
                 "comment prendre", "quelle dose", "dose maximale", "dose max", "quand prendre", "nakhod", "nakhdo",
                 "nakhd", "nchreb", "kifach nakhod", "chhal mn", "ch7al mn", "شحال من حبه", "شحال من مره", "ناخد", "ناخذ",
                 "جرعه", "كم مره", "كم حبه", "كيفاش ناخد", "how many", "how often", "dosage for"],
    "medical_advice": ["j ai mal", "mal a la", "mal au", "mal de", "symptome", "symptomes", "diagnostic", "que prendre",
                       "quoi prendre", "je peux prendre", "puis je prendre", "peut on prendre", "est ce dangereux",
                       "enceinte", "allaitement", "j allaite", "mon bebe", "mon enfant", "quel medicament pour",
                       "traitement pour", "soigner", "guerir", "kan7ess", "kat7ess", "3ndi l7rara", "3ndi lhrara",
                       "nqder nakhod", "n9der nakhod", "wach nqder", "wach n9der", "ach nakhod", "chno nakhod",
                       "كنحس", "كتحس", "حامل", "كنرضع", "واش نقدر", "شنو ناخد", "اش ناخد", "عندي الحراره", "علاج",
                       "what should i take", "can i take", "i have pain"],
    "price": ["prix", "combien coute", "coute", "cout", "tarif", "ppv", "cher", "taman", "tamane", "tmn", "ch7al",
              "chhal", "chehal", "bch7al", "bchhal", "9adach", "ثمن", "تمن", "التمن", "بشحال", "شحال", "سعر", "قداش",
              "price", "cost", "dirham", "dh"],
    "active_ingredient": ["substance active", "substance", "principe actif", "composition", "molecule", "compose de",
                          "contient", "dci", "chno fih", "ach fih", "mn chno", "المادة الفعالة", "الماده الفعاله", "ماده فعاله",
                          "الماده", "المكونات", "تركيبه", "التركيبه", "شنو فيه", "active ingredient", "ingredient"],
    "dosages": ["dosage", "dosages", "concentration", "existe en", "quels mg", "combien de mg", "mg disponibles",
                "عيار", "الجرعات", "الدوزاج", "dozaj", "dosaj", "strength", "strengths"],
    "presentations": ["presentation", "presentations", "boite", "boites", "conditionnement", "format", "forme",
                      "comprimes par boite", "3olba", "l3olba", "علبه", "العلبه", "شكل", "packaging", "pack"],
    "generics": ["generique", "generiques", "equivalent", "equivalents", "princeps", "biosimilaire", "moins cher",
                 "remplacer", "remplacant", "alternative", "badil", "bdil", "جنيس", "الجنيس", "بديل", "البديل", "البدائل",
                 "generic", "generics"],
    "indications": ["indication", "indications", "sert a", "a quoi sert", "utilise pour", "utilise contre",
                    "pour quoi faire", "dyal ach", "3lach kaydir", "3lach kayslah", "kayslah", "علاش كيصلح", "كيصلح",
                    "لاش كيصلح", "استعمال", "used for", "what is it for"],
    "precautions": ["precaution", "precautions", "contre indication", "contre indications", "mise en garde",
                    "mises en garde", "effets indesirables", "effet indesirable", "effets secondaires",
                    "effet secondaire", "interaction", "interactions", "risque", "risques", "alcool", "موانع",
                    "احتياطات", "الاعراض الجانبيه", "اعراض جانبيه", "تداخل", "side effects", "contraindication"],
    "on_duty": ["de garde", "garde", "nuit", "ouverte maintenant", "24h", "24 h", "الحراسه", "حراسه", "dyal lil",
                "f lil", "on duty", "night"],
    "pharmacy_search": ["pharmacie", "pharmacies", "officine", "saydaliya", "saydalia", "saydlia", "farmasyan",
                        "fermasyan", "صيدليه", "صيدليات", "الصيدليه", "فرمسيان", "pharmacy"],
    "availability": ["disponible", "disponibilite", "en stock", "stock", "rupture", "kayn", "kayen", "kayna",
                     "wach kayn", "واش كاين", "كاين", "متوفر", "available", "in stock"],
    "greeting": ["bonjour", "bonsoir", "salut", "salam", "slm", "coucou", "merci", "chokran", "choukran",
                 "السلام", "سلام", "شكرا", "hello", "hi", "thanks"],
    "help": ["aide", "aidez moi", "que peux tu faire", "que sais tu faire", "comment ca marche", "3awni", "عاوني",
             "شنو كتعرف", "help"],
}
# Intentions qui exigent un médicament pour être traitées
MEDICINE_INTENTS = {"price", "active_ingredient", "dosages", "presentations", "generics", "indications", "precautions",
                    "posology", "availability", "medicine_info"}
SAFETY_INTENTS = ("emergency", "posology", "medical_advice")
_PRIORITY = {name: i for i, name in enumerate(INTENT_PATTERNS)}
_NORMALIZED = {intent: [normalize_text(p) for p in pats] for intent, pats in INTENT_PATTERNS.items()}
TRIGGER_TOKENS = {tok for pats in _NORMALIZED.values() for p in pats for tok in p.split()}


@dataclass
class IntentResult:
    name: str
    confidence: float
    matched: list[str] = field(default_factory=list)
    alternatives: list[dict] = field(default_factory=list)

    def summary(self) -> dict:
        return {"name": self.name, "confidence": round(self.confidence, 2), "matched": self.matched,
                "alternatives": self.alternatives}


def _token_hit(pattern: str, tokens: list[str], expanded: set[str]) -> bool:
    if pattern in expanded:
        return True
    # tolérance aux fautes uniquement pour les mots latins assez longs (« generiqe », « posologi »)
    if len(pattern) >= 6 and not has_arabic(pattern):
        return any(len(t) >= 5 and fuzz.ratio(pattern, t) >= 85 for t in tokens)
    return False


def detect_intent(message: str) -> IntentResult:
    norm = normalize_text(message)
    tokens = norm.split()
    expanded = {v for t in tokens for v in (arabic_variants(t) if has_arabic(t) else [t])}
    padded = f" {norm} "
    scores: dict[str, tuple[float, list[str]]] = {}
    for intent, patterns in _NORMALIZED.items():
        hits = []
        for p in patterns:
            if (" " in p and f" {p} " in padded) or (" " not in p and _token_hit(p, tokens, expanded)):
                hits.append(p)
        if hits:
            # une expression de plusieurs mots est plus spécifique qu'un mot isolé
            scores[intent] = (sum(1.0 + 0.5 * p.count(" ") for p in hits), hits)
    if not scores:
        return IntentResult("unknown", 0.0)
    for intent in SAFETY_INTENTS:  # la sécurité prime, quel que soit le score des autres intentions
        if intent in scores:
            best = intent
            break
    else:
        best = max(scores, key=lambda k: (scores[k][0], -_PRIORITY[k]))
    total = sum(s for s, _ in scores.values())
    alternatives = [{"name": k, "score": round(v[0], 1)} for k, v in
                    sorted(scores.items(), key=lambda kv: (-kv[1][0], _PRIORITY[kv[0]])) if k != best][:3]
    conf = min(1.0, 0.5 + 0.5 * scores[best][0] / total) if total else 0.0
    return IntentResult(best, conf, scores[best][1], alternatives)
