import Link from "next/link";

export default function ModulePending({ title, intro, items, lot }: { title: string; intro: string; items: string[]; lot: string }) {
  return (
    <div className="mx-auto max-w-page px-5 py-14">
      <h1 className="display text-4xl">{title}</h1>
      <p className="prose-copy mt-4 text-lg text-muted">{intro}</p>
      <div className="mt-10 grid gap-10 md:grid-cols-[1.4fr_1fr]">
        <div>
          <p className="label-wide text-sm">Ce que fera ce module ({lot})</p>
          <ul className="mt-4 space-y-3">
            {items.map((t) => <li key={t} className="border-l-2 border-health pl-3">{t}</li>)}
          </ul>
        </div>
        <div className="rounded-xl border border-ink/10 bg-white p-6">
          <p className="font-semibold">Déjà disponible</p>
          <p className="mt-2 text-sm text-muted">Le catalogue s&apos;appuie sur la même base : recherche tolérante aux fautes, prix sourcés, génériques et pharmacies.</p>
          <Link href="/medicines" className="mt-5 inline-block rounded-lg bg-clinic px-4 py-2.5 text-sm font-semibold text-white">Explorer les médicaments</Link>
        </div>
      </div>
    </div>
  );
}
