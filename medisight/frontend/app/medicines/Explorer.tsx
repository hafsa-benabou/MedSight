"use client";
import { ArrowRight, Info, Loader2, PackageSearch, Search, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { CARD, EmptyState, Spinner } from "@/components/PageShell";
import { ErrorBox } from "@/components/States";
import { Stamp } from "@/components/Stamp";
import { api, type MedicineCard, type SearchResult } from "@/lib/api";
import { day, mad } from "@/lib/format";

const EXAMPLES = ["amlor 5mg", "amlodipine", "abilify 10 mg", "a.v.t", "amlor 20 mg"];
// Statut princeps/générique tel qu'indiqué par la source AMMPS ; aucune équivalence n'est déduite côté interface
const TYPE: Record<string, string> = { P: "Princeps", G: "Générique" };

const norm = (s: string | null | undefined) => (s ?? "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9.,]/g, "");
const composition = (m: MedicineCard) => m.ingredients.map((i) => norm(i.name)).sort().join("+");

type Group = { title: string; note?: string; items: MedicineCard[] };

/** Regroupe uniquement lorsque la recherche désigne un nom commercial précis présent dans les résultats ; sinon liste neutre. */
function groupResults(data: SearchResult): Group[] | null {
  const brand = norm((data.meta.did_you_mean ?? data.meta.query_normalized).split(" ")[0]);
  const dose = norm(data.meta.dosage_requested);
  if (!brand) return null;
  const exact = data.items.filter((m) => norm(m.brand) === brand && (!dose || norm(m.dosage) === dose));
  if (!exact.length || exact.length === data.items.length) return null;
  const comps = new Set(exact.map(composition).filter(Boolean));
  const rest = data.items.filter((m) => !exact.includes(m));
  const same = rest.filter((m) => comps.has(composition(m)));
  const other = rest.filter((m) => !same.includes(m));
  return [
    { title: "Correspondance exacte", items: exact },
    { title: "Médicaments de même composition", items: same,
      note: "Même substance active selon les sources importées. Les équivalences génériques officielles sont détaillées sur chaque fiche." },
    { title: "Autres résultats", items: other },
  ].filter((g) => g.items.length > 0);
}

export default function Explorer({ initialQuery }: { initialQuery: string }) {
  const [q, setQ] = useState(initialQuery);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    const t = setTimeout(() => {
      const params = new URLSearchParams({ q, page: String(page), size: "15" });
      setError(null);
      api<SearchResult>(`/api/medicines/search?${params}`, ctrl.signal)
        .then((d) => { setData(d); setLoading(false); })
        .catch((e: Error) => { if (e.name !== "AbortError") { setError(e.message); setLoading(false); } });
    }, 250);
    return () => { clearTimeout(t); ctrl.abort(); };
  }, [q, page, attempt]);

  const update = (v: string) => { setQ(v); setPage(1); };
  const pages = data ? Math.max(1, Math.ceil(data.total / data.size)) : 1;
  const meta = data?.meta;
  const groups = data && page === 1 && q.trim() ? groupResults(data) : null;

  return (
    <section className="mt-8">
      <div className={`${CARD} p-4 md:p-5`}>
        <label htmlFor="q" className="sr-only">Médicament, substance ou dosage</label>
        <div className="flex items-center gap-2 rounded-xl border border-ink/15 bg-paper/60 px-3 transition focus-within:border-clinic focus-within:bg-white focus-within:ring-4 focus-within:ring-clinic/10">
          {loading ? <Loader2 aria-hidden className="h-5 w-5 shrink-0 animate-spin text-clinic" /> : <Search aria-hidden className="h-5 w-5 shrink-0 text-muted" />}
          <input id="q" type="search" value={q} autoComplete="off" placeholder="Nom commercial, substance active ou dosage (ex. amlor 5 mg)"
            onChange={(e) => update(e.target.value)}
            className="min-h-12 w-full bg-transparent text-base outline-none placeholder:text-muted/80 md:text-lg [&::-webkit-search-cancel-button]:hidden" />
          {q && (
            <button onClick={() => update("")} aria-label="Effacer la recherche" className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-muted transition hover:bg-white hover:text-ink">
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
          <span className="text-xs text-muted">Essayez :</span>
          {EXAMPLES.map((ex) => (
            <button key={ex} onClick={() => update(ex)}
              className={`rounded-full border px-3 py-1 text-xs transition ${norm(q) === norm(ex) ? "border-health bg-mint font-semibold text-[#0E5F51]" : "border-ink/15 bg-white hover:border-health/50 hover:bg-mint"}`}>{ex}</button>
          ))}
        </div>
        <p className="mt-3 flex gap-1.5 text-xs text-muted"><Info aria-hidden className="mt-px h-3.5 w-3.5 shrink-0 text-clinic" />
          Les fautes de frappe sont tolérées ; le dosage demandé n&apos;est jamais remplacé par un autre.</p>
      </div>

      <div className="mt-5 space-y-3" aria-live="polite">
        {meta?.did_you_mean && data && data.total > 0 && (
          <Banner>Résultats pour <strong>{meta.did_you_mean}</strong> (orthographe rapprochée de « {q} »).</Banner>
        )}
        {meta?.dosage_found === false && (
          <Banner>Aucune présentation à <strong>{meta.dosage_requested}</strong> n&apos;est référencée. Dosages disponibles : <strong>{meta.available_dosages.join(", ")}</strong>. Le dosage n&apos;est jamais remplacé automatiquement.</Banner>
        )}
      </div>

      {error ? <ErrorBox message={error} onRetry={() => setAttempt((a) => a + 1)} /> : !data ? <Spinner label="Recherche dans le catalogue…" /> : (
        <div className={`transition-opacity ${loading ? "opacity-60" : ""}`}>
          <p className="mt-5 text-sm text-muted" role="status">
            <strong className="text-ink">{data.total}</strong> médicament{data.total > 1 ? "s" : ""} {q.trim() ? <>pour « <bdi>{q.trim()}</bdi> »</> : "dans le catalogue"}
            {pages > 1 && ` · page ${page} sur ${pages}`}
          </p>
          {data.total === 0 && meta?.dosage_found !== false && (
            <div className={`${CARD} mt-3`}>
              <EmptyState Icon={PackageSearch} title={`Aucun médicament ne correspond à « ${q.trim()} »`}>
                Aucun résultat dans les sources importées. Vérifiez l&apos;orthographe ou cherchez par substance active (ex. amlodipine).
              </EmptyState>
            </div>
          )}
          {groups ? groups.map((g) => (
            <div key={g.title} className="mt-6">
              <h2 className="flex items-baseline gap-2 text-xs font-semibold uppercase tracking-[0.1em] text-[#11806B]">{g.title}<span className="font-normal text-muted">{g.items.length}</span></h2>
              {g.note && <p className="mt-1 text-xs text-muted">{g.note}</p>}
              <ResultList items={g.items} />
            </div>
          )) : <ResultList items={data.items} />}
          {pages > 1 && (
            <nav aria-label="Pagination" className="mt-6 flex items-center justify-center gap-3 text-sm">
              <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="rounded-lg border border-ink/15 bg-white px-4 py-2 font-semibold transition hover:border-ink disabled:opacity-40">Précédent</button>
              <span className="text-muted">Page {page} sur {pages}</span>
              <button disabled={page >= pages} onClick={() => setPage(page + 1)} className="rounded-lg border border-ink/15 bg-white px-4 py-2 font-semibold transition hover:border-ink disabled:opacity-40">Suivant</button>
            </nav>
          )}
        </div>
      )}
    </section>
  );
}

function Banner({ children }: { children: React.ReactNode }) {
  return <p className="flex gap-2 rounded-xl border border-clinic/25 bg-[#E6F1F7] px-4 py-3 text-sm text-ink"><Info aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-clinic" /><span>{children}</span></p>;
}

function ResultList({ items }: { items: MedicineCard[] }) {
  if (!items.length) return null;
  return <ul className="mt-3 grid gap-3 md:grid-cols-2">{items.map((m) => <ResultCard key={m.id} m={m} />)}</ul>;
}

/** Carte compacte : seules les valeurs renvoyées par l'API sont affichées ; un prix absent reste signalé absent. */
function ResultCard({ m }: { m: MedicineCard }) {
  const priced = m.presentations.find((p) => p.ppv != null && p.ppv === m.min_ppv);
  const asOf = day(priced?.price_as_of);
  const substances = m.ingredients.map((i) => i.name).join(" + ");
  return (
    <li className="group flex flex-col rounded-xl border border-ink/10 bg-white p-4 shadow-[0_6px_18px_-14px_rgba(18,59,93,0.3)] transition hover:border-health/40 motion-safe:hover:-translate-y-0.5">
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1.5">
        <p dir="ltr" className="min-w-0"><span className="display text-lg">{m.brand}</span>{m.dosage && <span className="ml-1.5 font-semibold text-clinic">{m.dosage}</span>}</p>
        <span className="flex flex-wrap items-center gap-1.5">
          {m.princeps_status && TYPE[m.princeps_status] && (
            <span title="Statut indiqué par la source" className="rounded-full bg-paper px-2 py-0.5 text-[11px] font-semibold text-muted">{TYPE[m.princeps_status]}</span>
          )}
          <Stamp status={m.data_status} />
        </span>
      </div>
      <dl className="mt-3 space-y-1 text-sm">
        <Row k="Substance active" v={substances || null} />
        <Row k="Forme" v={m.form} />
        <Row k="Laboratoire" v={m.laboratory} />
        <Row k="Prix" v={m.min_ppv != null ? `${m.presentations.length > 1 ? "À partir de " : ""}${mad(m.min_ppv)} (PPV${asOf ? `, au ${asOf}` : ""})` : null} missing="Prix non disponible" />
      </dl>
      <div className="mt-auto flex flex-wrap items-center justify-between gap-2 pt-4">
        <span className="min-w-0 truncate text-xs text-muted">{m.source ? `Source : ${m.source.name}` : ""}</span>
        <Link href={`/medicines/${m.id}`} className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-ink px-3 py-2 text-xs font-semibold text-white transition hover:bg-[#0d2f4b]">
          Voir la fiche <ArrowRight aria-hidden className="h-3.5 w-3.5 transition motion-safe:group-hover:translate-x-0.5" />
        </Link>
      </div>
    </li>
  );
}

function Row({ k, v, missing = "Non renseigné" }: { k: string; v: string | null; missing?: string }) {
  return (
    <div className="grid grid-cols-[7rem_minmax(0,1fr)] gap-2">
      <dt className="text-muted">{k}</dt>
      <dd className={`break-words ${v ? "" : "text-muted"}`}>{v ?? missing}</dd>
    </div>
  );
}
