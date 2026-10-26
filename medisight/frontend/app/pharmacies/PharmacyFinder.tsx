"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { SourceStamp } from "@/components/Stamp";
import { ErrorBox, Loading, Notice } from "@/components/States";
import { api, type DutyShift, type MedicineDetail, type PharmacySearch } from "@/lib/api";
import { time } from "@/lib/format";

const CITIES = ["Casablanca", "Rabat", "Marrakech", "Tanger", "Fès", "Agadir", "Salé", "Témara", "Mohammedia", "Béni Mellal"];

export default function PharmacyFinder({ medicineId, initialCity }: { medicineId: string | null; initialCity: string }) {
  const [city, setCity] = useState(initialCity);
  const [data, setData] = useState<PharmacySearch | null>(null);
  const [duty, setDuty] = useState<DutyShift[] | null>(null);
  const [med, setMed] = useState<MedicineDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!medicineId) return;
    api<MedicineDetail>(`/api/medicines/${medicineId}`).then(setMed).catch(() => setMed(null));
  }, [medicineId]);

  useEffect(() => {
    const ctrl = new AbortController();
    const params = new URLSearchParams({ city });
    if (medicineId) params.set("medicine_id", medicineId);
    setError(null);
    setData(null);
    Promise.all([
      api<PharmacySearch>(`/api/pharmacies/search?${params}`, ctrl.signal),
      api<{ items: DutyShift[] }>(`/api/pharmacies/on-duty?city=${encodeURIComponent(city)}`, ctrl.signal),
    ]).then(([p, d]) => { setData(p); setDuty(d.items); }).catch((e: Error) => { if (e.name !== "AbortError") setError(e.message); });
    return () => ctrl.abort();
  }, [city, medicineId, attempt]);

  return (
    <section className="mt-8">
      {med && <Notice>Disponibilité recherchée pour <strong>{med.brand} {med.dosage}</strong>. <Link href={`/medicines/${med.id}`} className="underline">Voir la fiche</Link></Notice>}
      <label htmlFor="city" className="label-wide mt-6 block text-sm">Ville</label>
      <select id="city" value={city} onChange={(e) => setCity(e.target.value)} className="mt-2 rounded-lg border border-ink/20 bg-white px-3 py-2.5">
        {CITIES.map((c) => <option key={c}>{c}</option>)}
      </select>
      {error ? <ErrorBox message={error} onRetry={() => setAttempt((a) => a + 1)} /> : !data ? <Loading /> : (
        <div className="mt-8 grid gap-10 md:grid-cols-[1.6fr_1fr]">
          <div>
            <div className="rounded-lg border-l-4 border-clinic bg-white px-4 py-3 text-sm font-semibold">{data.stock_notice}</div>
            <p className="mt-4 text-sm text-muted">{data.total} pharmacie{data.total > 1 ? "s" : ""} à {data.city}</p>
            {data.total === 0 && <p className="py-6 text-muted">Aucune pharmacie référencée à {data.city} dans les données importées. Importez OpenStreetMap ou le registre AMMPS complet.</p>}
            <ul className="mt-2 divide-y divide-ink/10 border-y border-ink/10 bg-white">
              {data.items.map((p) => (
                <li key={p.id} className="px-4 py-4">
                  <p className="font-semibold">{p.name}</p>
                  <p className="text-sm text-muted">{p.address ?? "Adresse non disponible dans cette source"}{p.phone ? `, ${p.phone}` : ""}</p>
                  {p.availability && (
                    <p className={`mt-1 text-sm ${p.availability.kind === "simulated" ? "text-sim" : "text-muted"}`}>
                      {p.availability.kind === "verified" ? `Stock vérifié : ${p.availability.status}` : p.availability.kind === "simulated"
                        ? `${p.availability.label} (${p.availability.status === "in_stock" ? "en stock" : p.availability.status === "low" ? "stock faible" : "rupture"})`
                        : "Stock non vérifié"}
                    </p>
                  )}
                  <div className="mt-2"><SourceStamp status={p.data_status} source={p.source} /></div>
                </li>
              ))}
            </ul>
          </div>
          <aside>
            <h2 className="display text-2xl">De garde maintenant</h2>
            {!duty?.length ? <p className="mt-3 text-sm text-muted">Aucune garde importée pour {data.city} à cette heure. Consultez les listes officielles de garde de votre ville.</p> : (
              <ul className="mt-4 space-y-4">
                {duty.map((s, i) => (
                  <li key={i} className="rounded-xl border border-ink/10 bg-white p-4 text-sm">
                    <p className="font-semibold">{s.pharmacy_name}</p>
                    <p className="text-muted">Garde de {s.shift_type}, {time(s.starts_at)} au {time(s.ends_at)}</p>
                    <div className="mt-2"><SourceStamp status={s.data_status} source={s.source} /></div>
                  </li>
                ))}
              </ul>
            )}
          </aside>
        </div>
      )}
    </section>
  );
}
