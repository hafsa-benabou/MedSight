import Link from "next/link";
import SourcesList from "@/components/SourcesList";
import { Stamp } from "@/components/Stamp";

const STATUSES: [string, string][] = [
  ["official", "Donnée d'une autorité publique (AMMPS, CNOPS), avec sa date de version."],
  ["reference", "Source scientifique tierce reconnue (ex. DDInter pour les interactions)."],
  ["unverified", "Donnée non vérifiée (ex. OpenStreetMap, liste de garde saisie)."],
  ["simulated", "Donnée fictive de démonstration, supprimable en une commande."],
];

const CHALLENGES: [string, string, string[], string][] = [
  ["Challenge 1", "Chatbot pharmaceutique multilingue", [
    "Normalisation du message (accents, chiffres arabes, arabizi « ch7al », unités « 500mg »).",
    "Détection de la langue : français, arabe, darija en alphabet arabe ou latin.",
    "Détection de l'intention (prix, substance, dosages, génériques, pharmacie…) ; urgences et avis médicaux traités en priorité.",
    "Extraction des entités : médicament (fautes et écriture arabe tolérées), dosage, ville.",
    "Recherche dans PostgreSQL puis réponse rédigée à partir des seules données trouvées, avec leurs sources.",
  ], "/chat"],
  ["Challenge 2", "Pill Identifier", [
    "Contrôle de la photo : format, taille, netteté, luminosité.",
    "Lecture du code-barres EAN-13 / DataMatrix GS1.",
    "OCR Tesseract (français, arabe, anglais) sur plusieurs variantes et orientations de l'image.",
    "Extraction du nom, du dosage, de la substance, de la forme et du conditionnement.",
    "Rapprochement avec les présentations marocaines : indice expliqué, dosage jamais substitué.",
  ], "/identify"],
];

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-page px-5 py-14">
      <h1 className="display text-4xl">À propos</h1>
      <p className="prose-copy mt-4 text-lg text-muted">MEDISIGHT est un projet d&apos;ingénierie en Data Science (ChallengeCamp, INPT Rabat) : un assistant d&apos;information pharmaceutique adapté au Maroc, multilingue, qui cite ses sources.</p>
      <section className="mt-12 grid gap-px overflow-hidden rounded-2xl border border-ink/10 bg-ink/10 md:grid-cols-2">
        {CHALLENGES.map(([kicker, title, steps, href]) => (
          <article key={title} className="bg-white p-6">
            <p className="label-wide text-sm text-clinic">{kicker}</p>
            <h2 className="display mt-1 text-2xl">{title}</h2>
            <ol className="mt-4 space-y-2 text-sm">
              {steps.map((s, i) => <li key={s} className="grid grid-cols-[1.5rem_1fr]"><span className="font-semibold text-health">{i + 1}.</span><span>{s}</span></li>)}
            </ol>
            <Link href={href} className="mt-5 inline-block text-sm font-semibold text-clinic underline underline-offset-4">Essayer</Link>
          </article>
        ))}
      </section>
      <p className="prose-copy mt-6 text-sm text-muted">Les deux modules s&apos;appuient sur la même base PostgreSQL : un médicament reconnu sur une photo est transmis au chatbot par son identifiant en base, jamais par un simple nom recopié.</p>
      <section className="mt-12 grid gap-10 md:grid-cols-2">
        <div>
          <h2 className="display text-2xl">Avertissement médical</h2>
          <p className="prose-copy mt-3">MEDISIGHT n&apos;établit pas de diagnostic et ne remplace pas un pharmacien ou un médecin. En cas d&apos;urgence : SAMU 141 ou Protection civile 15.</p>
          <h2 className="display mt-10 text-2xl">Confidentialité</h2>
          <p className="prose-copy mt-3">Les photos ne sont pas conservées par défaut. Les conversations ont une durée de conservation limitée. Aucune donnée n&apos;est transmise à un service d&apos;IA externe sans consentement explicite.</p>
        </div>
        <div>
          <h2 className="display text-2xl">Statuts des données</h2>
          <ul className="mt-4 space-y-3 text-sm">
            {STATUSES.map(([s, t]) => <li key={s} className="grid grid-cols-[7rem_1fr] items-start gap-3"><span><Stamp status={s} /></span><span>{t}</span></li>)}
          </ul>
        </div>
      </section>
      <section id="sources" className="mt-14">
        <h2 className="display text-2xl">Sources chargées</h2>
        <div className="mt-4"><SourcesList /></div>
      </section>
    </div>
  );
}
