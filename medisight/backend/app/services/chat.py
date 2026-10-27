"""Assistant conversationnel MEDISIGHT : message -> normalisation -> langue -> intention -> entités -> PostgreSQL ->
réponse construite à partir des seules données sourcées (génération contrôlée par gabarits, sans LLM par défaut).

Règles : aucune donnée inventée (prix, stock, posologie, contre-indication, interaction, garde) ; une donnée absente
est annoncée comme absente ; les données simulées sont signalées ; jamais de diagnostic ni de traitement personnalisé.
Confidentialité : le texte saisi par l'utilisateur n'est pas conservé en base (seule son analyse l'est, 72 h)."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app import models as m
from app.core.config import Settings
from app.ingestion.common import utcnow
from app.nlp.entities import STOPWORDS, Entities, extract_entities, load_vocabulary
from app.nlp.intents import MEDICINE_INTENTS, TRIGGER_TOKENS, IntentResult, detect_intent
from app.nlp.language import LanguageGuess, detect_language
from app.nlp.text import normalize_text
from app.services import catalog, pharmacies
from app.services.catalog import _LOAD, medicine_card, source_ref

MAX_MEDS = 6
EXCERPT = 700
PRECAUTION_SECTIONS = ("contraindications", "warnings", "interactions", "pregnancy", "side_effects")
SECTION_FOR = {"indications": ("indications",), "precautions": PRECAUTION_SECTIONS, "posology": ("posology",)}
_FIRST_NUMBER = re.compile(r"\d+(?:\.\d+)?")

T: dict[str, dict[str, str]] = {
    "disclaimer": {"fr": "Information documentaire, pas un avis médical : demandez conseil à votre pharmacien ou médecin. "
                         "Urgence : SAMU 141, Protection civile 15.",
                   "ar": "معلومات توثيقية وليست استشارة طبية: اسأل الصيدلي أو الطبيب. في حالة الاستعجال: الإسعاف 141، الوقاية المدنية 15."},
    "emergency": {"fr": "Si la situation est urgente (malaise, surdosage, intoxication, idées suicidaires), appelez immédiatement "
                        "le SAMU au 141 ou la Protection civile au 15. Centre Antipoison et de Pharmacovigilance du Maroc : {poison}. "
                        "Je ne peux pas évaluer une situation médicale.",
                  "ar": "إذا كانت الحالة مستعجلة (تسمم، جرعة زائدة، فقدان الوعي)، اتصل فوراً بالإسعاف 141 أو الوقاية المدنية 15. "
                        "المركز المغربي لمحاربة التسمم: {poison}. لا يمكنني تقييم حالة طبية."},
    "medical_advice": {"fr": "Je ne peux ni établir de diagnostic ni recommander un traitement personnalisé. Pour cette question, "
                             "adressez-vous à un pharmacien ou à un médecin, qui tiendra compte de votre situation.",
                       "ar": "لا يمكنني تقديم تشخيص أو وصف علاج شخصي. لهذا السؤال، توجه إلى صيدلي أو طبيب يأخذ وضعك بعين الاعتبار."},
    "offer_facts": {"fr": "Je peux en revanche vous donner les informations documentées sur {med} (composition, présentations, prix).",
                    "ar": "يمكنني في المقابل أن أعطيك المعلومات الموثقة عن {med} (التركيبة، العلب، الثمن)."},
    "greeting": {"fr": "Bonjour ! Je suis l'assistant MEDISIGHT. Posez-moi une question sur un médicament (prix, substance active, "
                       "dosages, génériques) ou cherchez une pharmacie par ville. Je réponds en français, en arabe et en darija.",
                 "ar": "مرحباً! أنا مساعد MEDISIGHT. اسألني عن دواء (الثمن، المادة الفعالة، العيارات، الأدوية الجنيسة) أو ابحث عن صيدلية حسب المدينة."},
    "help": {"fr": "Exemples : « Prix du Doliprane 500 mg », « Quelle est la substance active d'AMLOR ? », « Génériques d'AMLOR 5 mg », "
                   "« Pharmacie à Rabat », « ch7al taman dyal Doliprane ? ». Les réponses viennent de la base MEDISIGHT et citent leur source.",
             "ar": "أمثلة: « شحال ثمن Doliprane 500mg »، « شنو المادة الفعالة ديال AMLOR »، « صيدلية في الرباط ». الأجوبة مأخوذة من قاعدة MEDISIGHT مع ذكر المصدر."},
    "unknown": {"fr": "Je n'ai pas compris votre demande. Précisez le nom du médicament et ce que vous cherchez (prix, substance active, "
                      "dosages, génériques, pharmacie…).",
                "ar": "لم أفهم طلبك. حدد اسم الدواء وما تبحث عنه (الثمن، المادة الفعالة، العيار، الجنيس، صيدلية…)."},
    "which_medicine": {"fr": "De quel médicament parlez-vous ? Indiquez son nom (et si possible son dosage), par exemple « AMLOR 5 mg ».",
                       "ar": "عن أي دواء تتحدث؟ اذكر اسمه (والعيار إن أمكن)، مثلاً « AMLOR 5 mg »."},
    "not_found": {"fr": "Je ne trouve pas « {q} » dans la base MEDISIGHT. Vérifiez l'orthographe ; la base de démonstration ne contient "
                        "qu'un échantillon du Répertoire AMMPS.",
                  "ar": "لم أجد « {q} » في قاعدة MEDISIGHT. تحقق من الإملاء؛ قاعدة العرض تحتوي فقط على عينة من سجل AMMPS."},
    "did_you_mean": {"fr": "Je n'ai pas trouvé exactement « {q} ». Vouliez-vous dire {brand} ?",
                     "ar": "لم أجد « {q} » بالضبط. هل تقصد {brand}؟"},
    "dose_missing": {"fr": "{brand} n'est pas référencé au dosage {dose} dans nos sources. Dosages disponibles : {available}. "
                           "Je ne remplace jamais un dosage par un autre.",
                     "ar": "{brand} غير مسجل بعيار {dose} في مصادرنا. العيارات المتوفرة: {available}. لا أعوض عياراً بآخر أبداً."},
    "price_head": {"fr": "Prix publics (PPV) de {med} :", "ar": "الثمن العمومي (PPV) لـ {med}:"},
    "no_price": {"fr": "prix non disponible dans nos sources", "ar": "الثمن غير متوفر في مصادرنا"},
    "fake_price": {"fr": "prix FICTIF (donnée simulée de démonstration)", "ar": "ثمن وهمي (معطى تجريبي)"},
    "ingredient": {"fr": "{med} contient : {ings}.", "ar": "{med} يحتوي على: {ings}."},
    "no_ingredient": {"fr": "La composition de {med} n'est pas renseignée dans nos sources.",
                      "ar": "تركيبة {med} غير متوفرة في مصادرنا."},
    "dosages": {"fr": "{brand} est référencé aux dosages suivants : {list}.", "ar": "{brand} مسجل بالعيارات التالية: {list}."},
    "presentations_head": {"fr": "Présentations de {med} :", "ar": "علب {med}:"},
    "no_presentation": {"fr": "Aucune présentation n'est renseignée pour {med}.", "ar": "لا توجد علب مسجلة لـ {med}."},
    "generics_reg": {"fr": "Groupe générique du Répertoire AMMPS « {group} » : {members}.",
                     "ar": "مجموعة الأدوية الجنيسة في سجل AMMPS « {group} »: {members}."},
    "generics_pharma": {"fr": "Même composition (correspondance non réglementaire) : {list}.",
                        "ar": "نفس التركيبة (تطابق غير تنظيمي): {list}."},
    "no_generics": {"fr": "Aucun générique de {med} n'est référencé dans nos sources.",
                    "ar": "لا يوجد دواء جنيس لـ {med} مسجل في مصادرنا."},
    "generics_note": {"fr": "Seules les équivalences du Répertoire AMMPS sont réglementaires ; toute substitution se décide avec votre pharmacien.",
                      "ar": "التعادلات المسجلة في سجل AMMPS وحدها تنظيمية؛ أي تعويض يتم مع الصيدلي."},
    "section_head": {"fr": "{title} de {med} (source : {source}{date}) :", "ar": "{title} — {med} (المصدر: {source}{date}):"},
    "section_missing": {"fr": "Les {topic} de {med} ne sont pas disponibles dans nos sources. Consultez la notice de la boîte et "
                              "demandez conseil à votre pharmacien.",
                        "ar": "{topic} الخاصة بـ {med} غير متوفرة في مصادرنا. راجع النشرة داخل العلبة واسأل الصيدلي."},
    "posology_warning": {"fr": "La posologie dépend de votre situation (âge, poids, autres traitements) : seul votre médecin ou "
                               "pharmacien peut vous l'indiquer.",
                         "ar": "الجرعة تختلف حسب حالتك (السن، الوزن، الأدوية الأخرى): الطبيب أو الصيدلي وحده يمكنه تحديدها."},
    "interaction_line": {"fr": "Interaction documentée {a} + {b} ({severity}) : {desc}", "ar": "تداخل موثق {a} + {b} ({severity}): {desc}"},
    "ask_city": {"fr": "Dans quelle ville cherchez-vous une pharmacie ? (ex. « pharmacie à Rabat »)",
                 "ar": "في أي مدينة تبحث عن صيدلية؟ (مثلاً « صيدلية في الرباط »)"},
    "pharmacies_head": {"fr": "Pharmacies référencées à {city} ({n}) :", "ar": "الصيدليات المسجلة في {city} ({n}):"},
    "no_pharmacy": {"fr": "Aucune pharmacie n'est référencée à {city} dans nos sources.", "ar": "لا توجد صيدلية مسجلة في {city} في مصادرنا."},
    "duty_head": {"fr": "Pharmacies de garde à {city} en ce moment :", "ar": "صيدليات الحراسة في {city} الآن:"},
    "no_duty": {"fr": "Aucune garde vérifiée n'est enregistrée pour {city} en ce moment. Renseignez-vous auprès de la préfecture "
                      "ou en appelant le 141 la nuit.",
                "ar": "لا توجد حراسة موثقة مسجلة في {city} حالياً. استفسر لدى العمالة أو اتصل بـ 141 ليلاً."},
    "stock_unverified": {"fr": "Le stock en pharmacie n'est pas vérifié : appelez la pharmacie pour confirmer la disponibilité.",
                         "ar": "المخزون في الصيدليات غير مؤكد: اتصل بالصيدلية للتأكد من توفر الدواء."},
    "marketing": {"fr": "Statut de commercialisation de {med} selon l'AMMPS : {status}.",
                  "ar": "وضعية تسويق {med} حسب AMMPS: {status}."},
    "info": {"fr": "{med} — {form} ; substance(s) : {ings} ; laboratoire : {lab} ; {status}.",
             "ar": "{med} — {form}؛ المادة الفعالة: {ings}؛ المختبر: {lab}؛ {status}."},
    "simulated_flag": {"fr": "SIMULATION — fiche de démonstration, données fictives", "ar": "محاكاة — معطيات وهمية للعرض"},
    "simulated_warning": {"fr": "Cette réponse contient des données SIMULÉES (démonstration) : elles ne sont pas réelles.",
                          "ar": "يحتوي هذا الجواب على معطيات محاكاة (للعرض فقط) وليست حقيقية."},
    "from_context": {"fr": "(Médicament de la conversation : {med}.)", "ar": "(الدواء موضوع المحادثة: {med}.)"},
}
TOPIC = {"indications": {"fr": "indications", "ar": "دواعي الاستعمال"},
         "precautions": {"fr": "précautions, contre-indications et effets indésirables", "ar": "الاحتياطات وموانع الاستعمال"},
         "posology": {"fr": "informations de posologie", "ar": "معلومات الجرعة"}}


def t(key: str, lang: str, **kw) -> str:
    return T[key].get(lang, T[key]["fr"]).format(**kw)


def money(v: float | Decimal | None) -> str:
    return f"{float(v):,.2f}".replace(",", " ").replace(".", ",") + " DH" if v is not None else "—"


def med_label(med: m.Medicine) -> str:
    return " ".join(x for x in (med.brand_name, med.dosage_text) if x)


@dataclass
class Reply:
    lines: list[str] = field(default_factory=list)
    meds: list[m.Medicine] = field(default_factory=list)
    pharmacies: list[dict] = field(default_factory=list)
    sources: dict[str, dict] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    understanding: str = "understood"
    simulated: bool = False

    def source(self, src: m.DataSource | None, data_status: str | None = None) -> None:
        ref = source_ref(src)
        if ref:
            ref = {**ref, "data_status": data_status or src.default_data_status}
            self.sources.setdefault(ref["code"], ref)
        if data_status == "simulated":
            self.simulated = True


# --- Résolution du médicament -------------------------------------------------------------------------------------

@dataclass
class Resolution:
    meds: list[m.Medicine] = field(default_factory=list)
    brand_meds: list[m.Medicine] = field(default_factory=list)  # tous les dosages de la marque
    from_context: bool = False
    query: str | None = None
    did_you_mean: str | None = None
    dose_missing: bool = False


def _dose_matches(med: m.Medicine, ent: Entities) -> bool:
    d = ent.dose
    if d is None:
        return True
    if d.mg is not None:
        return any(mi.strength_mg is not None and float(mi.strength_mg) == d.mg for mi in med.ingredients)
    norm = normalize_text(med.dosage_text or "")
    if d.unit is None:
        first = _FIRST_NUMBER.search(norm)
        return bool(first) and float(first.group()) == d.value
    return f"{d.value:g} {normalize_text(d.unit)}" in norm


def _residual(message: str, ent: Entities) -> str:
    skip = set(STOPWORDS) | TRIGGER_TOKENS | set((ent.city_text or "").split()) | set((ent.dose.text if ent.dose else "").split())
    return " ".join(tok for tok in normalize_text(message).split() if tok not in skip and not tok.isdigit() and len(tok) >= 3)


def _load_brand(db: Session, brands: list[str]) -> list[m.Medicine]:
    stmt = select(m.Medicine).options(*_LOAD).where(m.Medicine.brand_normalized.in_(brands))
    meds = list(db.scalars(stmt).unique())
    return sorted(meds, key=lambda x: (brands.index(x.brand_normalized), x.data_status == "simulated", x.dosage_text or ""))


def resolve(db: Session, message: str, ent: Entities, context: m.Medicine | None, intent: str) -> Resolution:
    res = Resolution()
    brands = [x.brand for x in ent.medicines]
    if brands:
        res.brand_meds = _load_brand(db, brands)
    elif ent.ingredients and intent not in ("generics",):
        ids = [x.ingredient_id for x in ent.ingredients]
        res.brand_meds = list(db.scalars(select(m.Medicine).options(*_LOAD).join(m.MedicineIngredient)
                                         .where(m.MedicineIngredient.ingredient_id.in_(ids))
                                         .order_by(m.Medicine.brand_normalized).limit(40)).unique())
    elif ent.ingredients:
        res.brand_meds = list(db.scalars(select(m.Medicine).options(*_LOAD).join(m.MedicineIngredient)
                                         .where(m.MedicineIngredient.ingredient_id == ent.ingredients[0].ingredient_id)
                                         .limit(1)).unique())
    else:
        residual = _residual(message, ent)
        if residual and intent in MEDICINE_INTENTS | {"unknown"}:
            found = catalog.search_medicines(db, residual, size=MAX_MEDS)
            if found["items"]:
                res.did_you_mean = found["meta"].get("did_you_mean")
                res.brand_meds = _load_brand(db, [normalize_text(found["items"][0]["brand"])])
            elif intent in MEDICINE_INTENTS and not context:
                res.query = residual
        if not res.brand_meds and context is not None and intent in MEDICINE_INTENTS:
            res.brand_meds, res.from_context = [context], True
            return _finish(res, ent, ignore_dose=True)
    if res.did_you_mean:
        res.query = _residual(message, ent)
    return _finish(res, ent)


def _finish(res: Resolution, ent: Entities, ignore_dose: bool = False) -> Resolution:
    if ignore_dose or ent.dose is None:
        res.meds = res.brand_meds[:MAX_MEDS]
    else:
        res.meds = [x for x in res.brand_meds if _dose_matches(x, ent)][:MAX_MEDS]
        res.dose_missing = bool(res.brand_meds) and not res.meds
    return res


# --- Réponses par intention ---------------------------------------------------------------------------------------

def _flag(med_or_status, lang: str) -> str:
    status = med_or_status if isinstance(med_or_status, str) else med_or_status.data_status
    return f" [{t('simulated_flag', lang)}]" if status == "simulated" else ""


def answer_price(r: Reply, meds: list[m.Medicine], lang: str) -> None:
    for med in meds:
        r.lines.append(t("price_head", lang, med=med_label(med)) + _flag(med, lang))
        r.source(med.source, med.data_status)
        if not med.presentations:
            r.lines.append(f"• {t('no_price', lang)}")
        for p in med.presentations:
            r.source(p.source, p.data_status)
            if p.ppv_mad is None:
                r.lines.append(f"• {p.label} : {t('no_price', lang)}")
                continue
            extra = f" — {t('fake_price', lang)}" if p.data_status == "simulated" else ""
            asof = f", au {p.price_as_of.isoformat()}" if p.price_as_of else ""
            src = p.source.name if p.source else "?"
            r.lines.append(f"• {p.label} : {money(p.ppv_mad)} (PPV{asof} ; source : {src}){extra}")


def _ings(med: m.Medicine) -> str:
    return ", ".join(f"{mi.ingredient.name}" + (f" ({mi.strength_text})" if mi.strength_text else "") for mi in med.ingredients)


def answer_ingredient(r: Reply, meds: list[m.Medicine], lang: str) -> None:
    seen = set()
    for med in meds:
        key = (med.brand_normalized, _ings(med))
        if key in seen:
            continue
        seen.add(key)
        r.source(med.source, med.data_status)
        r.lines.append((t("ingredient", lang, med=med_label(med), ings=_ings(med)) if med.ingredients
                        else t("no_ingredient", lang, med=med_label(med))) + _flag(med, lang))


def answer_dosages(r: Reply, brand_meds: list[m.Medicine], lang: str) -> None:
    by_brand: dict[str, list[m.Medicine]] = {}
    for med in brand_meds:
        by_brand.setdefault(med.brand_name, []).append(med)
        r.source(med.source, med.data_status)
    for brand, meds in by_brand.items():
        items = sorted({f"{x.dosage_text or '?'} ({x.form.label.lower() if x.form else 'forme non précisée'})"
                        + (" — simulé" if x.data_status == "simulated" else "") for x in meds})
        r.lines.append(t("dosages", lang, brand=brand, list=", ".join(items)))


def answer_presentations(r: Reply, meds: list[m.Medicine], lang: str) -> None:
    for med in meds:
        r.source(med.source, med.data_status)
        if not med.presentations:
            r.lines.append(t("no_presentation", lang, med=med_label(med)))
            continue
        r.lines.append(t("presentations_head", lang, med=med_label(med)) + _flag(med, lang))
        for p in med.presentations:
            r.source(p.source, p.data_status)
            ean = f" — EAN {p.ean13}" if p.ean13 else ""
            r.lines.append(f"• {p.label}{ean}" + (f" ({med.form.label.lower()})" if med.form else ""))


def answer_generics(db: Session, r: Reply, meds: list[m.Medicine], lang: str) -> None:
    med = meds[0]
    g = catalog.generics_for(db, med.id)
    r.source(med.source, med.data_status)
    found = False
    for grp in g["regulatory"]:
        found = True
        members = "; ".join(f"{x['label']} ({'princeps' if x['type'] == 'P' else 'générique' if x['type'] == 'G' else '?'})"
                            for x in grp["members"] if not x["is_current"])
        r.lines.append(t("generics_reg", lang, group=grp["group"], members=members or "—"))
        r.sources.setdefault(grp["source"]["code"], {**grp["source"], "data_status": grp["data_status"]})
    pharma = [c for c in g["pharmacological"] if c["data_status"] != "simulated" or med.data_status == "simulated"]
    if pharma:
        found = True
        r.lines.append(t("generics_pharma", lang, list=", ".join(
            f"{c['brand']} {c['dosage'] or ''}".strip() + (" (simulé)" if c["data_status"] == "simulated" else "")
            for c in pharma[:8])))
        ids = [c["id"] for c in pharma[:4]]
        r.meds.extend(db.scalars(select(m.Medicine).options(*_LOAD).where(m.Medicine.id.in_(ids))).unique())
    if not found:
        r.lines.append(t("no_generics", lang, med=med_label(med)))
    r.lines.append(t("generics_note", lang))


def answer_sections(db: Session, r: Reply, meds: list[m.Medicine], lang: str, intent: str) -> None:
    med = meds[0]
    codes = SECTION_FOR[intent]
    sections = db.scalars(select(m.ClinicalSection).options(selectinload(m.ClinicalSection.source))
                          .where(m.ClinicalSection.medicine_id == med.id, m.ClinicalSection.section_code.in_(codes))).all()
    sections = sorted(sections, key=lambda s: codes.index(s.section_code))
    for s in sections:
        date = f", {s.document_date.isoformat()}" if s.document_date else ""
        r.lines.append(t("section_head", lang, title=s.title, med=med_label(med), source=s.source.name, date=date))
        content = s.content.strip()
        r.lines.append(content if len(content) <= EXCERPT else content[:EXCERPT].rsplit(" ", 1)[0] + " … (suite dans la fiche)")
        r.source(s.source, s.data_status)
    interactions_found = False
    if intent == "precautions":
        ing_ids = [mi.ingredient_id for mi in med.ingredients]
        if ing_ids:
            rows = db.scalars(select(m.DrugInteraction).options(selectinload(m.DrugInteraction.source))
                              .where(or_(m.DrugInteraction.ingredient_a_id.in_(ing_ids),
                                         m.DrugInteraction.ingredient_b_id.in_(ing_ids))).limit(8)).all()
            names = {i.id: i.name for i in db.scalars(select(m.ActiveIngredient).where(m.ActiveIngredient.id.in_(
                {x.ingredient_a_id for x in rows} | {x.ingredient_b_id for x in rows})))} if rows else {}
            for x in rows:
                interactions_found = True
                r.lines.append(t("interaction_line", lang, a=names.get(x.ingredient_a_id, "?"), b=names.get(x.ingredient_b_id, "?"),
                                 severity=x.severity_raw or x.severity, desc=x.description or "—"))
                r.source(x.source, x.data_status)
    if not sections and not interactions_found:
        r.understanding = "information_unavailable"
        r.lines.append(t("section_missing", lang, topic=TOPIC[intent][lang if lang in ("fr", "ar") else "fr"], med=med_label(med)))
    if intent == "posology":
        r.lines.append(t("posology_warning", lang))


def answer_info(r: Reply, meds: list[m.Medicine], lang: str) -> None:
    for med in meds:
        r.source(med.source, med.data_status)
        status = med.marketing_status or "statut de commercialisation non renseigné"
        r.lines.append(t("info", lang, med=med_label(med), form=med.form.label.lower() if med.form else "forme non précisée",
                         ings=_ings(med) or "non renseignée", lab=med.laboratory.name if med.laboratory else "non renseigné",
                         status=status) + _flag(med, lang))
        prices = [p for p in med.presentations if p.ppv_mad is not None]
        if prices:
            cheapest = min(prices, key=lambda p: p.ppv_mad)
            extra = f" — {t('fake_price', lang)}" if cheapest.data_status == "simulated" else ""
            r.lines.append(f"• PPV : {money(cheapest.ppv_mad)} ({cheapest.label}){extra}")


def answer_pharmacies(db: Session, r: Reply, ent: Entities, med: m.Medicine | None, lang: str, intent: str) -> None:
    if not ent.city:
        r.understanding = "clarification_needed"
        r.lines.append(t("ask_city", lang))
        return
    if intent == "on_duty":
        duty = pharmacies.on_duty(db, ent.city)
        if not duty["items"]:
            r.understanding = "information_unavailable"
            r.lines.append(t("no_duty", lang, city=ent.city))
            return
        r.lines.append(t("duty_head", lang, city=ent.city))
        for s in duty["items"][:6]:
            r.lines.append(f"• {s['pharmacy_name']} — {s['address'] or 'adresse non renseignée'} — {s['phone'] or 'tél. non renseigné'} "
                           f"({s['shift_type']})" + _flag(s["data_status"], lang))
            if s["source"]:
                r.sources.setdefault(s["source"]["code"], {**s["source"], "data_status": s["data_status"]})
            r.simulated |= s["data_status"] == "simulated"
        return
    found = pharmacies.search_pharmacies(db, city=ent.city, medicine_id=med.id if med else None, limit=6)
    if not found["items"]:
        r.understanding = "information_unavailable"
        r.lines.append(t("no_pharmacy", lang, city=ent.city))
        return
    r.lines.append(t("pharmacies_head", lang, city=found["city"] or ent.city, n=found["total"]))
    for p in found["items"]:
        av = p.get("availability")
        avail = ""
        if av:
            avail = (" — stock VÉRIFIÉ : " + av["status"]) if av["kind"] == "verified" else (
                " — " + av["label"] if av.get("label") else "")
        r.lines.append(f"• {p['name']} — {p['address'] or 'adresse non renseignée'} — {p['phone'] or 'tél. non renseigné'}"
                       + _flag(p["data_status"], lang) + avail)
        if p["source"]:
            r.sources.setdefault(p["source"]["code"], {**p["source"], "data_status": p["data_status"]})
        r.simulated |= p["data_status"] == "simulated" or bool(av and av["kind"] == "simulated")
    r.pharmacies = found["items"]
    if med is not None:
        r.lines.append(t("stock_unverified", lang))


def answer_availability(db: Session, r: Reply, ent: Entities, meds: list[m.Medicine], lang: str) -> None:
    for med in meds[:3]:
        r.source(med.source, med.data_status)
        if med.marketing_status:
            r.lines.append(t("marketing", lang, med=med_label(med), status=med.marketing_status) + _flag(med, lang))
    if ent.city:
        answer_pharmacies(db, r, ent, meds[0], lang, "pharmacy_search")
    else:
        r.lines.append(t("stock_unverified", lang))


SUGGESTIONS = {
    "fr": ["Quelle est la substance active de {b} ?", "Quels sont les dosages disponibles de {b} ?",
           "Quelles sont les présentations de {m} ?", "Quels sont les génériques de {m} ?", "Quel est le prix de {m} ?"],
    "ar": ["شنو المادة الفعالة ديال {b}؟", "شنو العيارات ديال {b}؟", "شحال ثمن {m}؟", "واش كاين بديل ديال {m}؟"],
}
GENERIC_SUGGESTIONS = {
    "fr": ["Prix du Doliprane 500 mg", "Quelle est la substance active d'AMLOR 5 mg ?", "Génériques d'AMLOR 5 mg",
           "Je cherche une pharmacie à Rabat", "Ch7al taman dyal Doliprane 500mg ?"],
    "ar": ["شنو المادة الفعالة ديال AMLOR؟", "صيدلية في الرباط", "شحال ثمن Doliprane 500mg؟"],
}


def suggestions_for(med: m.Medicine | None, lang: str = "fr") -> list[str]:
    lang = lang if lang in SUGGESTIONS else "fr"
    if med is None:
        return GENERIC_SUGGESTIONS[lang]
    return [s.format(b=med.brand_name, m=med_label(med)) for s in SUGGESTIONS[lang]]


# --- Conversation -------------------------------------------------------------------------------------------------

def _conversation(db: Session, settings: Settings, conversation_id: str | None) -> m.Conversation:
    now = utcnow()
    conv = None
    if conversation_id:
        try:
            conv = db.get(m.Conversation, uuid.UUID(str(conversation_id)))
        except ValueError:
            conv = None
        if conv is not None and conv.expires_at <= now:
            conv = None
    if conv is None:
        conv = m.Conversation(expires_at=now + timedelta(hours=settings.conversation_retention_hours))
        db.add(conv)
        db.flush()
    conv.last_activity_at = now
    conv.expires_at = now + timedelta(hours=settings.conversation_retention_hours)
    return conv


def handle_message(db: Session, settings: Settings, message: str, *, conversation_id: str | None = None,
                   context_medicine_id: int | None = None, persist: bool = True) -> dict:
    lang_guess: LanguageGuess = detect_language(message)
    lang = lang_guess.reply_language
    intent: IntentResult = detect_intent(message)
    vocab = load_vocabulary(db)
    ent = extract_entities(message, vocab)
    conv = _conversation(db, settings, conversation_id)
    r = Reply()

    if context_medicine_id is not None:  # contexte transmis par le Pill Identifier : identifiant vérifié en base
        if db.get(m.Medicine, context_medicine_id) is not None:
            conv.context_medicine_id = context_medicine_id
        else:
            r.warnings.append("Contexte ignoré : médicament introuvable dans la base.")
    context = db.scalar(select(m.Medicine).options(*_LOAD).where(m.Medicine.id == conv.context_medicine_id)) \
        if conv.context_medicine_id else None

    name = intent.name
    if name == "unknown" and (ent.medicines or ent.ingredients):
        name = "medicine_info"
    if name in ("pharmacy_search", "on_duty", "greeting", "help", "unknown") and ent.city and name != "on_duty":
        name = "pharmacy_search"
    res = resolve(db, message, ent, context, name)
    if name == "unknown" and res.meds:
        name = "medicine_info"

    if name == "emergency":
        r.understanding = "emergency"
        r.lines.append(t("emergency", lang, poison=settings.poison_center))
    elif name == "medical_advice":
        r.understanding = "refused_medical_advice"
        r.lines.append(t("medical_advice", lang))
        if res.meds:
            r.lines.append(t("offer_facts", lang, med=med_label(res.meds[0])))
            r.meds = res.meds[:1]
    elif name == "greeting":
        r.lines.append(t("greeting", lang))
    elif name == "help":
        r.lines.append(t("help", lang))
    elif name in ("pharmacy_search", "on_duty"):
        answer_pharmacies(db, r, ent, res.meds[0] if res.meds and not res.from_context else None, lang, name)
    elif name in MEDICINE_INTENTS:
        if res.dose_missing:
            r.understanding = "dosage_not_found"
            available = sorted({x.dosage_text for x in res.brand_meds if x.dosage_text})
            r.lines.append(t("dose_missing", lang, brand=res.brand_meds[0].brand_name, dose=ent.dose.text,
                             available=", ".join(available) or "—"))
            r.meds = res.brand_meds[:MAX_MEDS]
        elif not res.meds:
            if res.query:
                r.understanding = "not_found"
                r.lines.append(t("not_found", lang, q=res.query))
            else:
                r.understanding = "clarification_needed"
                r.lines.append(t("which_medicine", lang))
        else:
            if res.did_you_mean:
                r.understanding = "ambiguous"
                r.lines.append(t("did_you_mean", lang, q=res.query, brand=res.did_you_mean))
            if res.from_context:
                r.lines.append(t("from_context", lang, med=med_label(res.meds[0])))
            r.meds = list(res.meds)
            if name == "price":
                answer_price(r, res.meds, lang)
            elif name == "active_ingredient":
                answer_ingredient(r, res.meds, lang)
            elif name == "dosages":
                answer_dosages(r, res.brand_meds or res.meds, lang)
            elif name == "presentations":
                answer_presentations(r, res.meds, lang)
            elif name == "generics":
                answer_generics(db, r, res.meds, lang)
            elif name in SECTION_FOR:
                answer_sections(db, r, res.meds, lang, name)
            elif name == "availability":
                answer_availability(db, r, ent, res.meds, lang)
            else:
                answer_info(r, res.meds, lang)
            if len({x.brand_normalized for x in res.meds}) == 1 and not res.did_you_mean:
                conv.context_medicine_id = res.meds[0].id  # pour les questions de suivi (« et son prix ? »)
    else:
        r.understanding = "not_understood"
        r.lines.append(t("unknown", lang))

    for med in r.meds:
        r.simulated |= med.data_status == "simulated"
    if r.simulated:
        r.warnings.append(t("simulated_warning", "fr"))
    if lang_guess.code == "darija_latin":
        r.warnings.append("Message en darija (alphabet latin) : réponse rédigée en français.")
    if intent.name == "unknown" and r.understanding == "understood":
        r.understanding = "partial"

    current = context if conv.context_medicine_id == (context.id if context else None) else \
        db.scalar(select(m.Medicine).options(*_LOAD).where(m.Medicine.id == conv.context_medicine_id))
    text = "\n".join(r.lines)
    medicines = []
    seen_ids: set[int] = set()
    for med in r.meds:
        if med.id not in seen_ids:
            seen_ids.add(med.id)
            medicines.append(medicine_card(med))
    analysis = {"language": lang_guess.summary(), "intent": {**intent.summary(), "resolved": name},
                "entities": ent.summary(), "understanding": r.understanding}
    conv.language = lang_guess.code
    if persist:
        # le texte de l'utilisateur n'est pas conservé (il peut contenir des données de santé) : seule l'analyse l'est
        db.add(m.Message(conversation_id=conv.id, role="user", content="[non conservé]", analysis=analysis))
        db.add(m.Message(conversation_id=conv.id, role="assistant", content=text,
                         sources=list(r.sources.values())))
        db.commit()
    return {
        "conversation_id": str(conv.id), "message": text, "language": lang_guess.summary(),
        "intent": {**intent.summary(), "resolved": name}, "entities": ent.summary(),
        "understanding": r.understanding, "medicines": medicines, "pharmacies": r.pharmacies,
        "sources": list(r.sources.values()), "warnings": list(dict.fromkeys(r.warnings)),
        "context_medicine": medicine_card(current) if current else None,
        "suggestions": suggestions_for(current or (r.meds[0] if r.meds else None), lang),
        "contains_simulated_data": r.simulated, "generation": "template", "disclaimer": t("disclaimer", lang),
    }
