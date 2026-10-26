import Link from "next/link";
import HeroDemo from "@/components/HeroDemo";
import SourcesList from "@/components/SourcesList";

const STEPS = [
  ["Vous demandez", "En français, en arabe ou en darija, à l'écrit, ou bientôt en photographiant une boîte."],
  ["MEDISIGHT interprète", "Langue, intention, médicament, dosage et ville sont extraits, puis cherchés dans des données sourcées."],
  ["Vous vérifiez", "Chaque réponse indique sa source et sa date. Un pharmacien confirme avant toute prise."],
];

export default function Home() {
  return (
    <>
      <section className="mx-auto grid max-w-page items-center gap-12 px-5 pb-20 pt-14 md:grid-cols-[1.05fr_1fr] md:pt-20">
        <div>
          <h1 className="display text-[2.6rem] text-ink md:text-[3.6rem]">Your Health, Our Intelligence</h1>
          <p className="prose-copy mt-6 text-lg text-muted">
            Discover medicines, get reliable pharmaceutical information, and explore AI-powered pill identification, all in one place.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/chat" className="rounded-lg bg-ink px-5 py-3 font-semibold text-white hover:bg-[#0d2f4b]">Talk to MediSight AI</Link>
            <Link href="/identify" className="rounded-lg border border-ink/25 bg-white px-5 py-3 font-semibold hover:border-ink">Identify a Pill</Link>
          </div>
          <p className="mt-6 text-sm text-muted">
            Disponible aujourd&apos;hui : <Link href="/medicines" className="font-semibold text-clinic underline underline-offset-4">le catalogue des médicaments</Link>, avec prix et génériques sourcés.
          </p>
        </div>
        <HeroDemo />
      </section>

      <section className="border-y border-ink/10 bg-white">
        <div className="mx-auto grid max-w-page gap-px bg-ink/10 md:grid-cols-[1.4fr_1fr]">
          <article className="bg-white px-5 py-12 md:px-10">
            <h2 className="display text-2xl">AI Pharmaceutical Assistant</h2>
            <p className="prose-copy mt-3 text-muted">Posez vos questions sur les médicaments vendus au Maroc. Les réponses s&apos;appuient uniquement sur les données importées et citent leur source.</p>
            <dl className="mt-6 grid gap-x-8 gap-y-3 text-sm sm:grid-cols-2">
              {[["Prix et remboursement", "PPV, PH, base CNOPS"], ["Génériques", "équivalences du Répertoire AMMPS"], ["Disponibilité", "pharmacies par ville, stock jamais supposé"], ["Interactions", "uniquement si documentées"]].map(([k, v]) => (
                <div key={k}><dt className="font-semibold">{k}</dt><dd className="text-muted">{v}</dd></div>
              ))}
            </dl>
            <div className="mt-8 flex flex-wrap gap-3 text-sm">
              <Link href="/medicines" className="rounded-lg bg-clinic px-4 py-2.5 font-semibold text-white">Explorer les médicaments</Link>
              <Link href="/chat" className="rounded-lg border border-ink/20 px-4 py-2.5 font-semibold">Voir l&apos;avancement du chatbot</Link>
            </div>
          </article>
          <article className="relative bg-white px-5 py-12 md:px-10">
            <div aria-hidden="true" className="pointer-events-none absolute inset-6 hidden md:block">
              <span className="absolute left-0 top-0 h-6 w-6 border-l-2 border-t-2 border-health" />
              <span className="absolute right-0 top-0 h-6 w-6 border-r-2 border-t-2 border-health" />
              <span className="absolute bottom-0 left-0 h-6 w-6 border-b-2 border-l-2 border-health" />
              <span className="absolute bottom-0 right-0 h-6 w-6 border-b-2 border-r-2 border-health" />
            </div>
            <h2 className="display text-2xl">AI Pill Identifier</h2>
            <p className="prose-copy mt-3 text-muted">Photographiez une boîte : le code-barres EAN-13 et le texte imprimé sont rapprochés du Répertoire AMMPS. Le résultat reste une hypothèse à faire confirmer.</p>
            <p className="mt-6 text-sm"><span className="font-semibold">État :</span> <span className="text-muted">module en développement.</span></p>
            <Link href="/identify" className="mt-8 inline-block rounded-lg border border-ink/20 px-4 py-2.5 text-sm font-semibold">Identify a Pill</Link>
          </article>
        </div>
      </section>

      <section className="mx-auto max-w-page px-5 py-20">
        <h2 className="display text-3xl">Comment ça marche</h2>
        <ol className="mt-10 grid gap-10 md:grid-cols-3">
          {STEPS.map(([title, text], i) => (
            <li key={title} className="border-t-2 border-ink pt-4">
              <span className="display text-4xl text-health">{i + 1}</span>
              <p className="mt-3 text-lg font-semibold">{title}</p>
              <p className="mt-2 text-muted">{text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="mx-auto grid max-w-page gap-12 px-5 md:grid-cols-[1.5fr_1fr]">
        <div>
          <h2 className="display text-3xl">Sources chargées</h2>
          <p className="prose-copy mt-3 text-muted">Liste lue en direct dans la base : chaque source est datée et qualifiée.</p>
          <div className="mt-6"><SourcesList /></div>
        </div>
        <div>
          <h2 className="display text-3xl">Limites</h2>
          <ul className="mt-6 space-y-4 text-sm">
            {["Aucun diagnostic ni conseil médical personnalisé.",
              "Posologie et effets indésirables affichés seulement s'ils proviennent d'un RCP ou d'une notice importés.",
              "Le stock d'une pharmacie n'est jamais supposé : il faut l'appeler pour confirmer.",
              "Une identification par photo est une hypothèse, à faire vérifier par un pharmacien.",
              "Les données de démonstration sont marquées « Simulé, démo »."].map((t) => (
              <li key={t} className="border-l-2 border-health pl-3">{t}</li>
            ))}
          </ul>
        </div>
      </section>
    </>
  );
}
