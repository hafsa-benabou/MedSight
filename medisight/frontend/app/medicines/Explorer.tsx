"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ErrorBox, Loading, Notice } from "@/components/States";
import { Stamp } from "@/components/Stamp";
import { api, type SearchResult } from "@/lib/api";
import { day, mad } from "@/lib/format";

const EXAMPLES = ["dolipran 500mg", "paracétamol", "amlodipine 5 mg", "a.v.t", "doliprane 750 mg"];
const FILTERS: [string, string][] = [["", "Tout"], ["official", "Officiel"], ["simulated", "Simulé, démo"]];

export default function Explorer({ initialQuery }: { initialQuery: string }) {
  const [q, setQ] = useState(initialQuery);
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<SearchResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const ctrl = new AbortController();
    const t = setTimeout(() => {
      const params = new URLSearchParams({ q, page: String(page), size: "15" });
      if (status) params.set("status", status);
      setError(null);
      api<SearchResult>(`/api/medicines/search?${params}`, ctrl.signal).then(setData).catch((e: Error) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    }, 250);
    return () => { clearTimeout(t); ctrl.abort(); };
  }, [q, status, page, attempt]);

  const pages = data ? Math.max(1, Math.ceil(data.total / data.size)) : 1;
  const meta = data?.meta;
  return (
    <section className="mt-8">
      <label htmlFor="q" className="label-wide text-sm">Médicament, substance ou dosage</label>
      <input id="q" type="search" value={q} autoComplete="off" placeholder="ex. dolipran 500mg"
        onChange={(e) => { setQ(e.target.value); setPage(1); }}
        className="mt-2 w-full rounded-xl border border-ink/20 bg-white px-4 py-3.5 text-lg outline-none focus:border-clinic" />
      <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted">Essayer :</span>
        {EXAMPLES.map((ex) => (
          <button key={ex} onClick={() => { setQ(ex); setPage(1); }} className="rounded-full border border-ink/15 bg-white px-3 py-1 hover:border-ink">{ex}</button>
        ))}
      </div>
      <div role="radiogroup" aria-label="Statut des données" className="mt-6 inline-flex rounded-lg border border-ink/15 bg-white p-1 text-sm">
        {FILTERS.map(([value, label]) => (
          <button key={value} role="radio" aria-checked={status === value} onClick={() => { setStatus(value); setPage(1); }}
            className={`rounded-md px-3 py-1.5 ${status === value ? "bg-ink text-white" : "text-muted hover:text-ink"}`}>{label}</button>
        ))}
      </div>

      <div className="mt-6 space-y-3" aria-live="polite">
        {meta?.did_you_mean && data && data.total > 0 && (
          <Notice>Résultats pour <strong>{meta.did_you_mean}</strong> (orthographe rapprochée de « {q} »).</Notice>
        )}
        {meta?.dosage_found === false && (
          <Notice>Aucune présentation à <strong>{meta.dosage_requested}</strong> n&apos;est référencée. Dosages disponibles : <strong>{meta.available_dosages.join(", ")}</strong>. Le dosage n&apos;est jamais remplacé automatiquement.</Notice>
        )}
      </div>

      {error ? <ErrorBox message={error} onRetry={() => setAttempt((a) => a + 1)} /> : !data ? <Loading label="Recherche…" /> : (
        <>
          <p className="mt-6 text-sm text-muted">{data.total} résultat{data.total > 1 ? "s" : ""}</p>
          {data.total === 0 && meta?.dosage_found !== false && (
            <p className="py-8 text-muted">Aucun médicament ne correspond à « {q} ». Vérifiez l&apos;orthographe ou cherchez par substance active.</p>
          )}
          <ul className="mt-2 divide-y divide-ink/10 border-y border-ink/10 bg-white">
            {data.items.map((m) => {
              const priced = m.presentations.find((p) => p.ppv != null);
              return (
                <li key={m.id}>
                  <Link href={`/medicines/${m.id}`} className="grid gap-3 px-4 py-5 hover:bg-paper md:grid-cols-[1fr_15rem] md:gap-8">
                    <div>
                      <p><span className="display text-xl">{m.brand}</span> <span className="label-wide ml-1 text-clinic">{m.dosage}</span></p>
                      <p className="mt-1 text-sm text-muted">{m.form}</p>
                      <p className="mt-1 text-sm">{m.ingredients.map((i) => i.name).join(" + ") || "Substance non renseignée"}{m.laboratory ? <span className="text-muted">, {m.laboratory}</span> : null}</p>
                    </div>
                    <div className="flex flex-col gap-1.5 md:items-end md:text-right">
                      <p className="font-semibold">{m.min_ppv != null ? `à partir de ${mad(m.min_ppv)}` : <span className="font-normal text-muted">Prix non disponible</span>}</p>
                      <Stamp status={m.data_status} />
                      {priced?.price_as_of && <span className="text-xs text-muted">prix au {day(priced.price_as_of)}</span>}
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
          {pages > 1 && (
            <nav aria-label="Pagination" className="mt-6 flex items-center gap-4 text-sm">
              <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="rounded-md border border-ink/20 bg-white px-3 py-1.5 disabled:opacity-40">Précédent</button>
              <span className="text-muted">Page {page} sur {pages}</span>
              <button disabled={page >= pages} onClick={() => setPage(page + 1)} className="rounded-md border border-ink/20 bg-white px-3 py-1.5 disabled:opacity-40">Suivant</button>
            </nav>
          )}
        </>
      )}
    </section>
  );
}
