"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { SourceStamp, Stamp } from "@/components/Stamp";
import { ErrorBox, Loading, Notice } from "@/components/States";
import { api, type Generics, type MedicineDetail } from "@/lib/api";
import { day, mad } from "@/lib/format";

const TYPE: Record<string, string> = { P: "Princeps", G: "Générique", I: "Type « I » (non documenté)" };

export default function MedicineDetailView({ id }: { id: string }) {
  const [med, setMed] = useState<MedicineDetail | null>(null);
  const [gen, setGen] = useState<Generics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const ctrl = new AbortController();
    setError(null);
    Promise.all([api<MedicineDetail>(`/api/medicines/${id}`, ctrl.signal), api<Generics>(`/api/medicines/${id}/generics`, ctrl.signal)])
      .then(([m, g]) => { setMed(m); setGen(g); })
      .catch((e: Error) => { if (e.name !== "AbortError") setError(e.message); });
    return () => ctrl.abort();
  }, [id, attempt]);

  if (error) return <div className="mx-auto max-w-page px-5 py-12"><ErrorBox message={error} onRetry={() => setAttempt((a) => a + 1)} /></div>;
  if (!med || !gen) return <div className="mx-auto max-w-page px-5"><Loading /></div>;

  return (
    <div className="mx-auto max-w-page px-5 py-10">
      <Link href="/medicines" className="text-sm text-clinic underline underline-offset-4">Retour au catalogue</Link>
      <header className="mt-6 overflow-hidden rounded-2xl border border-ink/15 bg-white">
        <div className={`h-2 ${med.data_status === "simulated" ? "bg-sim" : "bg-health"}`} />
        <div className="grid gap-6 px-6 py-7 md:grid-cols-[1fr_auto]">
          <div>
            <h1><span className="display text-4xl md:text-5xl">{med.brand}</span> <span className="label-wide ml-2 text-2xl text-clinic">{med.dosage}</span></h1>
            <p className="mt-2 text-muted">{med.form}{med.laboratory ? `, ${med.laboratory}` : ""}</p>
            <p className="mt-4 text-sm">
              <span className="font-semibold">Composition : </span>
              {med.ingredients.map((i) => `${i.name}${i.strength ? ` ${i.strength}` : ""}`).join(" + ") || "non renseignée"}
            </p>
            <p className="mt-1 text-sm"><span className="font-semibold">Statut de commercialisation : </span>{med.marketing_status ?? "non renseigné"}
              {med.princeps_status ? <span className="text-muted">, {TYPE[med.princeps_status] ?? med.princeps_status}</span> : null}</p>
          </div>
          <div className="md:text-right"><SourceStamp status={med.data_status} source={med.source} /></div>
        </div>
        {med.data_status === "simulated" && (
          <div className="border-t border-sim/30 bg-sim-soft px-6 py-3 text-sm text-[#6B3E00]">Fiche de démonstration : nom et composition réels, prix et présentations fictifs.</div>
        )}
      </header>

      <section className="mt-12">
        <h2 className="display text-2xl">Présentations et prix</h2>
        <div className="mt-4 overflow-x-auto rounded-xl border border-ink/10 bg-white">
          <table className="w-full min-w-[42rem] text-left text-sm">
            <thead className="bg-paper text-muted"><tr>
              <th className="px-4 py-3 font-medium">Présentation</th><th className="px-4 py-3 font-medium">PPV</th>
              <th className="px-4 py-3 font-medium">PH</th><th className="px-4 py-3 font-medium">Code EAN-13</th><th className="px-4 py-3 font-medium">Source</th>
            </tr></thead>
            <tbody className="divide-y divide-ink/10">
              {med.presentations.map((p) => (
                <tr key={p.id}>
                  <td className="px-4 py-3 font-medium">{p.label}</td>
                  <td className="px-4 py-3">{p.price_status === "no_price" ? <span className="text-muted">sans prix (AMM)</span> : mad(p.ppv)}</td>
                  <td className="px-4 py-3">{mad(p.ph)}</td>
                  <td className="px-4 py-3 tabular-nums">{p.ean13 ?? <span className="text-muted">non renseigné</span>}</td>
                  <td className="px-4 py-3"><SourceStamp status={p.data_status} source={p.source} date={p.price_as_of} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-sm"><Link href={`/pharmacies?medicine=${med.id}`} className="font-semibold text-clinic underline underline-offset-4">Où le trouver ?</Link> <span className="text-muted">Le stock n&apos;est jamais supposé.</span></p>
        <div className="mt-4">
          {med.reimbursements.length ? (
            <ul className="space-y-1 text-sm">{med.reimbursements.map((r, i) => (
              <li key={i}>Base de remboursement : <strong>{mad(r.base)}</strong>{r.rate != null ? `, taux ${r.rate} %` : ""} <SourceStamp status={r.data_status} source={r.source} date={r.valid_as_of} /></li>
            ))}</ul>
          ) : <p className="text-sm text-muted">Aucune donnée de remboursement importée pour ce médicament (référentiel CNOPS à importer).</p>}
        </div>
      </section>

      <section className="mt-12 grid gap-10 md:grid-cols-2">
        <div>
          <h2 className="display text-2xl">Équivalences réglementaires</h2>
          <p className="mt-2 text-sm text-muted">Groupes du Répertoire Marocain des Médicaments Génériques (AMMPS).</p>
          {gen.regulatory.length === 0 ? <p className="mt-4 text-sm text-muted">Ce médicament n&apos;appartient à aucun groupe générique importé.</p> :
            gen.regulatory.map((g) => (
              <div key={g.group} className="mt-4 rounded-xl border border-ink/10 bg-white">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-ink/10 px-4 py-3">
                  <p className="font-semibold">{g.group}</p><SourceStamp status={g.data_status} source={g.source} />
                </div>
                <ul className="divide-y divide-ink/10 text-sm">
                  {g.members.map((x) => (
                    <li key={x.label} className={`grid grid-cols-[6.5rem_1fr] gap-3 px-4 py-2.5 ${x.is_current ? "bg-mint/50" : ""}`}>
                      <span className="text-muted">{TYPE[x.type] ?? x.type}</span>
                      <span>{x.medicine_id && !x.is_current ? <Link href={`/medicines/${x.medicine_id}`} className="hover:underline">{x.label}</Link> : x.label}
                        <span className="block text-xs text-muted">{x.laboratory}{x.ean13 ? `, EAN ${x.ean13}` : ""}</span></span>
                    </li>
                  ))}
                </ul>
                {g.edition && <p className="px-4 py-2 text-xs text-muted">{g.edition}, version évolutive.</p>}
              </div>
            ))}
        </div>
        <div>
          <h2 className="display text-2xl">Même composition</h2>
          <p className="mt-2 text-sm text-muted">Même substance et même dosage. Correspondance pharmacologique, non vérifiée comme substituable.</p>
          {gen.pharmacological.length === 0 ? <p className="mt-4 text-sm text-muted">Aucune autre spécialité de même composition dans la base actuelle.</p> : (
            <ul className="mt-4 divide-y divide-ink/10 rounded-xl border border-ink/10 bg-white text-sm">
              {gen.pharmacological.map((c) => (
                <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
                  <Link href={`/medicines/${c.id}`} className="hover:underline"><span className="font-semibold">{c.brand} {c.dosage}</span>
                    <span className="block text-xs text-muted">{c.form}{c.same_form ? ", même forme" : ", forme différente"}</span></Link>
                  <span className="text-right">{mad(c.min_ppv)} <span className="ml-2"><Stamp status={c.data_status} /></span></span>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-4"><Notice>{gen.note}</Notice></div>
        </div>
      </section>

      <section className="mt-12">
        <h2 className="display text-2xl">Informations cliniques</h2>
        {med.clinical_sections.length === 0 ? (
          <div className="mt-4"><Notice>Aucune rubrique du RCP n&apos;a encore été importée pour ce médicament. MEDISIGHT n&apos;affiche ni posologie, ni contre-indications, ni effets indésirables sans source vérifiée.
            {med.rcp_url ? <> <a href={med.rcp_url} className="font-semibold underline" target="_blank" rel="noreferrer">Consulter le RCP</a>.</> : " Consultez la notice ou votre pharmacien."}</Notice></div>
        ) : med.clinical_sections.map((s) => (
          <article key={s.code} className="mt-6 border-l-2 border-clinic pl-4">
            <h3 className="font-semibold">{s.title}</h3>
            <p className="prose-copy mt-2 whitespace-pre-line text-sm">{s.content}</p>
            <div className="mt-2"><SourceStamp status={s.data_status} source={s.source} date={s.document_date} /></div>
          </article>
        ))}
      </section>
    </div>
  );
}
