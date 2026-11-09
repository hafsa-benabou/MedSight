import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import { ArrowRight, BookOpenCheck, BrainCircuit, Check, Info, MessagesSquare, ScanBarcode, ScanLine, Search, ShieldAlert } from "lucide-react";

type Module = { tag: string; title: string; text: string; points: string[]; note?: string; href: string; cta: string; Icon: LucideIcon; accent: string };

const MODULES: Module[] = [
  {
    tag: "Challenge 1 · NLP", title: "AI Pharmaceutical Assistant", Icon: MessagesSquare, accent: "bg-[#E6F1F7] text-clinic",
    text: "Un assistant conversationnel qui répond à vos questions sur les médicaments vendus au Maroc, à partir des seules données importées.",
    points: [
      "Questions en français, en arabe et en darija",
      "Recherche parmi les médicaments marocains",
      "Prix publics et substances actives, lorsqu'ils sont disponibles",
      "Génériques documentés par le Répertoire AMMPS",
      "Réponses fondées sur PostgreSQL et des sources identifiées",
    ],
    href: "/chat", cta: "Ouvrir le chatbot",
  },
  {
    tag: "Challenge 2 · Computer Vision", title: "AI Pill Identifier", Icon: ScanBarcode, accent: "bg-mint text-[#11806B]",
    text: "Un module de reconnaissance visuelle qui rapproche la photo d'une boîte de médicament du catalogue marocain.",
    points: [
      "Importation d'une photographie de la boîte",
      "OCR du texte imprimé et lecture du code-barres EAN-13",
      "Recherche des correspondances dans PostgreSQL",
      "Consultation des médicaments candidats, indice par indice",
      "Question directe au chatbot sur le résultat",
    ],
    note: "Chaque résultat est une hypothèse à faire confirmer par un pharmacien.",
    href: "/identify", cta: "Identifier une boîte",
  },
];

const STEPS: [LucideIcon, string, string][] = [
  [Search, "Vous recherchez ou importez une photographie", "Posez votre question en français, en arabe ou en darija, ou importez la photo d'une boîte."],
  [BrainCircuit, "MedSight analyse votre demande", "Les modules NLP ou Computer Vision extraient le médicament, le dosage ou le code-barres, puis interrogent la base."],
  [BookOpenCheck, "Vous consultez les informations et leurs sources", "Chaque réponse indique sa source et sa date. Un pharmacien confirme avant toute prise."],
];

const LIMITS = [
  "L'identification visuelle est une hypothèse, à faire confirmer.",
  "Prix et autres informations dépendent des données réellement disponibles et datées.",
  "Le stock d'une pharmacie n'est jamais supposé : appelez-la pour confirmer.",
  "Les données simulées sont clairement signalées « Simulé, démo ».",
];

const card = "rounded-2xl border border-ink/10 bg-white shadow-[0_1px_2px_rgba(18,59,93,0.04),0_12px_32px_-18px_rgba(18,59,93,0.18)]";

function HeroArt() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="hero-grid absolute inset-0" />
      <svg className="float-soft absolute -left-6 top-16 hidden w-40 text-clinic/25 md:block lg:left-8" viewBox="0 0 160 120" fill="none" stroke="currentColor" strokeWidth="2">
        <rect x="18" y="38" width="110" height="44" rx="22" transform="rotate(-24 73 60)" />
        <path d="M73 60l-18 -40" transform="rotate(-24 73 60) translate(18 0)" />
        <circle cx="140" cy="18" r="5" />
      </svg>
      <svg className="float-soft absolute right-0 top-10 hidden w-44 text-[#11806B]/25 md:block lg:right-10" style={{ animationDelay: "-3s" }} viewBox="0 0 180 160" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M60 40l26 15v30l-26 15-26-15V55z" />
        <path d="M86 55l26-15 26 15v30l-26 15-26-15" />
        <circle cx="60" cy="40" r="4" fill="currentColor" />
        <circle cx="138" cy="85" r="4" fill="currentColor" />
        <path d="M150 128h20M160 118v20" />
      </svg>
      <svg className="float-soft absolute bottom-10 left-[12%] hidden w-10 text-health/30 sm:block" style={{ animationDelay: "-1.5s" }} viewBox="0 0 40 40" fill="none" stroke="currentColor" strokeWidth="2.5">
        <path d="M14 4h12v10h10v12H26v10H14V26H4V14h10z" />
      </svg>
      <svg className="float-soft absolute bottom-16 right-[14%] hidden w-14 text-clinic/25 sm:block" style={{ animationDelay: "-4.5s" }} viewBox="0 0 56 56" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="28" cy="28" r="22" />
        <path d="M13 43L43 13" />
      </svg>
    </div>
  );
}

export default function Home() {
  return (
    <>
      <section className="hero-bg relative border-b border-ink/10">
        <HeroArt />
        <div className="relative mx-auto flex max-w-page flex-col items-center px-5 pb-20 pt-16 text-center md:pb-28 md:pt-24">
          <p className="fade-up inline-flex items-center gap-2 rounded-full border border-health/30 bg-white/80 px-3 py-1.5 text-[0.68rem] font-semibold uppercase tracking-[0.06em] sm:px-4 sm:text-xs sm:tracking-[0.12em] text-[#11806B] shadow-sm backdrop-blur">
            <span aria-hidden="true">✦</span> AI-Powered Pharmaceutical Platform
          </p>
          <h1 className="fade-up display hero-title mt-7 text-ink" style={{ animationDelay: "80ms" }}>
            Your Health,<br />
            <span className="bg-gradient-to-r from-clinic to-[#11806B] bg-clip-text text-transparent">Our Intelligence.</span>
          </h1>
          <p className="fade-up mt-7 text-lg font-semibold text-ink md:text-xl" style={{ animationDelay: "160ms" }}>
            Votre plateforme intelligente d&apos;information pharmaceutique au Maroc.
          </p>
          <p className="fade-up prose-copy mt-3 text-muted md:text-lg" style={{ animationDelay: "220ms" }}>
            MedSight réunit un chatbot pharmaceutique multilingue et un système de reconnaissance visuelle des boîtes de médicaments,
            tous deux adossés à un catalogue sourcé et daté.
          </p>
          <div className="fade-up mt-9 flex w-full flex-col justify-center gap-3 sm:w-auto sm:flex-row" style={{ animationDelay: "300ms" }}>
            <Link href="/chat" className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-ink px-6 font-semibold text-white shadow-[0_8px_20px_-10px_rgba(18,59,93,0.6)] transition hover:bg-[#0d2f4b] motion-safe:hover:-translate-y-0.5">
              <MessagesSquare size={18} aria-hidden="true" /> Discuter avec MedSight
            </Link>
            <Link href="/identify" className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-[#11806B] px-6 font-semibold text-white shadow-[0_8px_20px_-10px_rgba(17,128,107,0.6)] transition hover:bg-[#0c6a58] motion-safe:hover:-translate-y-0.5">
              <ScanLine size={18} aria-hidden="true" /> Identifier un médicament
            </Link>
          </div>
          <p className="fade-up mt-6 text-sm text-muted" style={{ animationDelay: "360ms" }}>
            Ou parcourez directement <Link href="/medicines" className="font-semibold text-clinic underline underline-offset-4 hover:text-ink">le catalogue des médicaments</Link>.
          </p>
        </div>
      </section>

      <section className="mx-auto max-w-page px-5 pt-20 md:pt-24" aria-labelledby="modules">
        <p className="text-center text-sm font-semibold uppercase tracking-[0.12em] text-[#11806B]">Deux challenges</p>
        <h2 id="modules" className="display mt-3 text-center text-3xl md:text-4xl">Deux modules, un même catalogue sourcé</h2>
        <div className="mt-12 grid gap-6 md:grid-cols-2">
          {MODULES.map(({ tag, title, text, points, note, href, cta, Icon, accent }) => (
            <article key={href} className={`${card} flex flex-col p-7 transition motion-safe:hover:-translate-y-1 md:p-9`}>
              <div className="flex items-center gap-4">
                <span className={`grid h-12 w-12 shrink-0 place-items-center rounded-xl ${accent}`}><Icon size={24} aria-hidden="true" /></span>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.1em] text-muted">{tag}</p>
                  <h3 className="display mt-1 text-xl md:text-2xl">{title}</h3>
                </div>
              </div>
              <p className="mt-5 leading-relaxed text-muted">{text}</p>
              <ul className="mt-6 space-y-3 text-sm">
                {points.map((p) => (
                  <li key={p} className="flex gap-3">
                    <Check size={18} aria-hidden="true" className="mt-px shrink-0 text-health" />
                    <span>{p}</span>
                  </li>
                ))}
              </ul>
              {note && (
                <p className="mt-6 flex gap-2 rounded-lg bg-sim-soft px-3 py-2 text-sm text-sim">
                  <Info size={16} aria-hidden="true" className="mt-0.5 shrink-0" /> {note}
                </p>
              )}
              <div className="mt-auto pt-8">
                <Link href={href} className="group inline-flex min-h-11 items-center gap-2 rounded-xl border border-ink/15 px-5 font-semibold transition hover:border-ink hover:bg-ink hover:text-white">
                  {cta} <ArrowRight size={18} aria-hidden="true" className="transition motion-safe:group-hover:translate-x-0.5" />
                </Link>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-page px-5 pt-20 md:pt-24" aria-labelledby="steps">
        <p className="text-center text-sm font-semibold uppercase tracking-[0.12em] text-[#11806B]">En trois étapes</p>
        <h2 id="steps" className="display mt-3 text-center text-3xl md:text-4xl">Comment ça marche</h2>
        <ol className="mt-12 grid gap-6 md:grid-cols-3">
          {STEPS.map(([Icon, title, text], i) => (
            <li key={title} className={`${card} relative p-7`}>
              <div className="flex items-center justify-between">
                <span className="grid h-12 w-12 place-items-center rounded-xl bg-ink text-white"><Icon size={22} aria-hidden="true" /></span>
                <span aria-hidden="true" className="display text-5xl text-ink/10">{String(i + 1).padStart(2, "0")}</span>
              </div>
              <p className="mt-6 text-lg font-semibold leading-snug"><span className="sr-only">Étape {i + 1} : </span>{title}</p>
              <p className="mt-2 text-sm leading-relaxed text-muted">{text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="mx-auto grid max-w-page gap-6 px-5 pt-20 md:grid-cols-2 md:pt-24" aria-label="Avertissement et limites">
        <article className={`${card} p-7`}>
          <div className="flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-lg bg-alert-soft text-alert"><ShieldAlert size={20} aria-hidden="true" /></span>
            <h2 className="display text-xl">Avertissement médical</h2>
          </div>
          <p className="mt-4 leading-relaxed text-muted">
            MedSight fournit des informations pharmaceutiques sourcées. Il ne pose aucun diagnostic et ne remplace pas l&apos;avis d&apos;un pharmacien ou d&apos;un médecin.
          </p>
          <p className="mt-4 rounded-lg bg-paper px-3 py-2 text-sm font-semibold">Urgence : SAMU 141 · Protection civile 15</p>
        </article>
        <article className={`${card} p-7`}>
          <div className="flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-lg bg-[#E6F1F7] text-clinic"><Info size={20} aria-hidden="true" /></span>
            <h2 className="display text-xl">Limites de la plateforme</h2>
          </div>
          <ul className="mt-4 space-y-2.5 text-sm">
            {LIMITS.map((t) => (
              <li key={t} className="flex gap-3"><span aria-hidden="true" className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-clinic" /><span>{t}</span></li>
            ))}
          </ul>
        </article>
      </section>
    </>
  );
}
