"use client";
import { Clock, Info, Loader2, MapPin, Phone, Pill, Search, Store, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { CARD, EmptyState, Spinner } from "@/components/PageShell";
import { SourceStamp } from "@/components/Stamp";
import { ErrorBox } from "@/components/States";
import { api, type DutyShift, type MedicineDetail, type Pharmacy, type PharmacySearch } from "@/lib/api";
import { time } from "@/lib/format";

const CITIES = ["Casablanca", "Rabat", "Marrakech", "Tanger", "Fès", "Agadir", "Salé", "Témara", "Mohammedia", "Béni Mellal"];

export default function PharmacyFinder({ medicineId, initialCity }: { medicineId: string | null; initialCity: string }) {
  const [city, setCity] = useState(initialCity);
  const [name, setName] = useState("");
  const [data, setData] = useState<PharmacySearch | null>(null);
  const [duty, setDuty] = useState<DutyShift[] | null>(null);
  const [med, setMed] = useState<MedicineDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!medicineId) return;
    api<MedicineDetail>(`/api/medicines/${medicineId}`).then(setMed).catch(() => setMed(null));
  }, [medicineId]);

  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    // Recherche par nom (paramètre q de l'API) : légère temporisation pendant la saisie
    const t = setTimeout(() => {
      const params = new URLSearchParams({ city });
      if (name.trim()) params.set("q", name.trim());
      if (medicineId) params.set("medicine_id", medicineId);
      setError(null);
      Promise.all([
        api<PharmacySearch>(`/api/pharmacies/search?${params}`, ctrl.signal),
        api<{ items: DutyShift[] }>(`/api/pharmacies/on-duty?city=${encodeURIComponent(city)}`, ctrl.signal),
      ]).then(([p, d]) => { setData(p); setDuty(d.items); setLoading(false); })
        .catch((e: Error) => { if (e.name !== "AbortError") { setError(e.message); setLoading(false); } });
    }, name ? 250 : 0);
    return () => { clearTimeout(t); ctrl.abort(); };
  }, [city, name, medicineId, attempt]);

  const shown = data?.city ?? city;
  return (
    <section className="mt-8">
      {med && (
        <p className="mb-4 flex flex-wrap items-center gap-2 rounded-xl border border-health/30 bg-mint/60 px-4 py-3 text-sm">
          <Pill aria-hidden className="h-4 w-4 text-[#11806B]" /> Disponibilité recherchée pour <strong>{med.brand} {med.dosage}</strong>
          <Link href={`/medicines/${med.id}`} className="font-semibold text-clinic underline underline-offset-2">Voir la fiche</Link>
        </p>
      )}

      <div className={`${CARD} grid gap-3 p-4 sm:grid-cols-[14rem_minmax(0,1fr)] md:p-5`}>
        <div>
          <label htmlFor="city" className="text-xs font-semibold uppercase tracking-[0.08em] text-muted">Ville</label>
          <div className="relative mt-1.5">
            <MapPin aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#11806B]" />
            <select id="city" value={city} onChange={(e) => setCity(e.target.value)}
              className="min-h-12 w-full appearance-none rounded-xl border border-ink/15 bg-paper/60 pl-9 pr-8 font-semibold text-ink outline-none transition focus:border-clinic focus:bg-white focus:ring-4 focus:ring-clinic/10">
              {CITIES.map((c) => <option key={c}>{c}</option>)}
            </select>
            <span aria-hidden className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted">▼</span>
          </div>
        </div>
        <div>
          <label htmlFor="pharmacy-name" className="text-xs font-semibold uppercase tracking-[0.08em] text-muted">Nom de la pharmacie (facultatif)</label>
          <div className="mt-1.5 flex items-center gap-2 rounded-xl border border-ink/15 bg-paper/60 px-3 transition focus-within:border-clinic focus-within:bg-white focus-within:ring-4 focus-within:ring-clinic/10">
            {loading ? <Loader2 aria-hidden className="h-4 w-4 shrink-0 animate-spin text-clinic" /> : <Search aria-hidden className="h-4 w-4 shrink-0 text-muted" />}
            <input id="pharmacy-name" type="search" value={name} onChange={(e) => setName(e.target.value)} autoComplete="off" placeholder="ex. Dounia"
              className="min-h-12 w-full bg-transparent outline-none placeholder:text-muted/80 [&::-webkit-search-cancel-button]:hidden" />
            {name && <button onClick={() => setName("")} aria-label="Effacer le nom" className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-muted hover:bg-white hover:text-ink"><X className="h-4 w-4" /></button>}
          </div>
        </div>
      </div>

      {error ? <ErrorBox message={error} onRetry={() => setAttempt((a) => a + 1)} /> : !data ? <Spinner label="Recherche des pharmacies…" /> : (
        <div className={`mt-6 grid items-start gap-6 transition-opacity lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)] ${loading ? "opacity-60" : ""}`}>
          <div>
            <p className="text-sm text-muted" role="status">
              <strong className="text-ink">{data.total}</strong> pharmacie{data.total > 1 ? "s" : ""} référencée{data.total > 1 ? "s" : ""} à <strong className="text-ink">{shown}</strong>
              {name.trim() && <> pour « <bdi>{name.trim()}</bdi> »</>}
            </p>
            <p className="mt-3 flex gap-2 rounded-xl border border-clinic/25 bg-[#E6F1F7] px-4 py-3 text-sm text-ink">
              <Info aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-clinic" />{data.stock_notice}
            </p>
            {data.total === 0 ? (
              <div className={`${CARD} mt-4`}>
                <EmptyState Icon={Store} title={name.trim() ? `Aucune pharmacie « ${name.trim()} » à ${shown}` : `Aucune pharmacie référencée à ${shown}`}>
                  Aucun établissement de cette ville n&apos;est encore présent dans les sources importées.
                </EmptyState>
              </div>
            ) : (
              <ul className="mt-4 grid gap-3 md:grid-cols-2">{data.items.map((p) => <PharmacyCard key={p.id} p={p} />)}</ul>
            )}
          </div>

          <aside aria-labelledby="duty-title" className={`${CARD} p-5`}>
            <div className="flex items-center gap-3">
              <span aria-hidden className="grid h-10 w-10 place-items-center rounded-xl bg-[#E6F1F7] text-clinic"><Clock size={20} /></span>
              <h2 id="duty-title" className="font-semibold text-ink">Pharmacies de garde</h2>
            </div>
            {!duty?.length ? (
              <p className="mt-4 text-sm leading-relaxed text-muted">Aucune information vérifiée sur les pharmacies de garde n&apos;est actuellement disponible pour cette ville.</p>
            ) : (
              <ul className="mt-4 space-y-3">
                {duty.map((s, i) => (
                  <li key={i} className="rounded-xl border border-ink/10 bg-paper/60 p-4 text-sm">
                    <p className="font-semibold">{s.pharmacy_name}</p>
                    <p className="mt-1 text-muted">Garde de {s.shift_type}, {time(s.starts_at)} au {time(s.ends_at)} (selon la source)</p>
                    {s.address && <p className="mt-1 text-muted">{s.address}</p>}
                    {s.phone && <p className="mt-1 text-muted">{s.phone}</p>}
                    <div className="mt-2"><SourceStamp status={s.data_status} source={s.source} /></div>
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-4 border-t border-ink/10 pt-3 text-xs text-muted">Appelez la pharmacie avant de vous déplacer : MedSight n&apos;indique jamais qu&apos;un établissement est ouvert sans information vérifiée.</p>
          </aside>
        </div>
      )}
    </section>
  );
}

/** Seules les valeurs présentes dans la source sont affichées ; un champ absent est signalé comme tel. */
function PharmacyCard({ p }: { p: Pharmacy }) {
  const rows: [typeof MapPin, string | null, string][] = [
    [MapPin, p.address ? `${p.address}${p.district ? `, ${p.district}` : ""}` : null, "Adresse non disponible dans cette source"],
    [Phone, p.phone, "Téléphone non disponible"],
    ...(p.opening_hours ? [[Clock, p.opening_hours, ""] as [typeof MapPin, string, string]] : []),
  ];
  return (
    <li className="flex flex-col rounded-xl border border-ink/10 bg-white p-4 shadow-[0_6px_18px_-14px_rgba(18,59,93,0.3)]">
      <div className="flex items-start gap-3">
        <span aria-hidden className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-mint text-[#11806B]"><Store size={18} /></span>
        <div className="min-w-0">
          <p className="font-semibold leading-snug text-ink">{p.name}</p>
          {p.city && <p className="text-xs text-muted">{p.city}</p>}
        </div>
      </div>
      <ul className="mt-3 space-y-1.5 text-sm">
        {rows.map(([Icon, v, missing]) => (
          <li key={missing || "hours"} className={`flex gap-2 ${v ? "" : "text-muted"}`}>
            <Icon aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-muted/70" /><span className="break-words">{v ?? missing}</span>
          </li>
        ))}
      </ul>
      {p.availability && (
        <p className={`mt-2 text-xs ${p.availability.kind === "simulated" ? "text-sim" : "text-muted"}`}>
          {p.availability.kind === "verified" ? `Stock vérifié : ${p.availability.status}` : p.availability.kind === "simulated"
            ? `${p.availability.label} (${p.availability.status === "in_stock" ? "en stock" : p.availability.status === "low" ? "stock faible" : "rupture"})`
            : "Stock non vérifié"}
        </p>
      )}
      <div className="mt-auto pt-3">
        {p.in_ammps_registry && <p className="mb-1.5 text-xs text-[#0E7563]">Inscrite au registre des pharmacies AMMPS</p>}
        <SourceStamp status={p.data_status} source={p.source} />
      </div>
    </li>
  );
}
