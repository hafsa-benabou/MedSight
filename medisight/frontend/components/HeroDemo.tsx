/** Exemple fixe d'interprétation structurée (le module NLP réel arrive au lot 2b). */
const TOKENS: { t: string; role?: string; delay?: number }[] = [
  { t: "slm" }, { t: "wach kayn", role: "intent", delay: 0.5 }, { t: "dolipran", role: "med", delay: 1.0 },
  { t: "f" }, { t: "casa", role: "city", delay: 1.5 }, { t: "?" },
];
const FIELDS: [string, string, number][] = [
  ["Langue", "darija (alphabet latin)", 2.0],
  ["Intention", "disponibilité d'un médicament", 2.25],
  ["Médicament", "Doliprane (« dolipran » corrigé)", 2.5],
  ["Ville", "Casablanca", 2.75],
  ["Stock", "non vérifié, à confirmer auprès de la pharmacie", 3.0],
];

export default function HeroDemo() {
  return (
    <figure className="rounded-2xl border border-ink/15 bg-white shadow-[0_1px_0_rgba(18,59,93,0.08)]">
      <div className="flex items-center justify-between rounded-t-2xl bg-ink px-5 py-3 text-white">
        <span className="label-wide text-sm">Requête reçue</span>
        <span className="text-xs text-white/70">exemple</span>
      </div>
      <p className="px-5 pt-5 text-2xl leading-relaxed md:text-[1.7rem]" lang="ary-Latn">
        {TOKENS.map((tok, i) => (
          <span key={i}>
            {tok.role ? <span className="parse-token px-0.5" style={{ animationDelay: `${tok.delay}s` }}>{tok.t}</span> : tok.t}{" "}
          </span>
        ))}
      </p>
      <dl className="mt-4 divide-y divide-ink/10 border-t border-ink/10 px-5 pb-2 text-sm">
        {FIELDS.map(([k, v, delay]) => (
          <div key={k} className="parse-field grid grid-cols-[7.5rem_1fr] gap-3 py-2.5" style={{ animationDelay: `${delay}s` }}>
            <dt className="text-muted">{k}</dt>
            <dd className="font-medium">{v}</dd>
          </div>
        ))}
      </dl>
      <figcaption className="rounded-b-2xl bg-paper px-5 py-3 text-xs text-muted">
        Interprétation structurée attendue du module NLP (en cours de développement).
      </figcaption>
    </figure>
  );
}
