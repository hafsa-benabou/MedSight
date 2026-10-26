import type { SourceRef } from "@/lib/api";
import { day } from "@/lib/format";

const STATUS: Record<string, [string, string]> = {
  official: ["Officiel", "border-health text-[#0E7563] bg-white"],
  reference: ["Référence", "border-clinic text-clinic bg-white"],
  unverified: ["Non vérifié", "border-muted/50 text-muted bg-white"],
  simulated: ["Simulé, démo", "border-sim text-sim bg-sim-soft"],
};

export function Stamp({ status }: { status: string }) {
  const [label, cls] = STATUS[status] ?? ["Statut inconnu", "border-muted text-muted bg-white"];
  return <span className={`inline-block rounded-[3px] border px-1.5 py-[3px] text-[11px] font-semibold leading-none ${cls}`}>{label}</span>;
}

/** Provenance d'une valeur : statut, source et date de version. */
export function SourceStamp({ status, source, date }: { status: string; source?: SourceRef; date?: string | null }) {
  const d = day(date);
  return (
    <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
      <Stamp status={status} />
      {source && (source.url
        ? <a href={source.url} target="_blank" rel="noreferrer" className="underline decoration-ink/20 underline-offset-2 hover:text-ink">{source.name}</a>
        : <span>{source.name}</span>)}
      {d && <span>version du {d}</span>}
    </span>
  );
}
