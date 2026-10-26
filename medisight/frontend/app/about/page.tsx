import SourcesList from "@/components/SourcesList";
import { Stamp } from "@/components/Stamp";

const STATUSES: [string, string][] = [
  ["official", "Donnée d'une autorité publique (AMMPS, CNOPS), avec sa date de version."],
  ["reference", "Source scientifique tierce reconnue (ex. DDInter pour les interactions)."],
  ["unverified", "Donnée non vérifiée (ex. OpenStreetMap, liste de garde saisie)."],
  ["simulated", "Donnée fictive de démonstration, supprimable en une commande."],
];

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-page px-5 py-14">
      <h1 className="display text-4xl">À propos</h1>
      <p className="prose-copy mt-4 text-lg text-muted">MEDISIGHT est un projet d&apos;ingénierie en Data Science (ChallengeCamp, INPT Rabat) : un assistant d&apos;information pharmaceutique adapté au Maroc, multilingue, qui cite ses sources.</p>
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
