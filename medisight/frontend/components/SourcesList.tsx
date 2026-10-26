"use client";
import { useEffect, useState } from "react";
import { api, type DataSourceInfo } from "@/lib/api";
import { day } from "@/lib/format";
import { ErrorBox, Loading } from "./States";
import { Stamp } from "./Stamp";

export default function SourcesList() {
  const [data, setData] = useState<DataSourceInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const ctrl = new AbortController();
    setError(null);
    api<DataSourceInfo[]>("/api/sources", ctrl.signal).then(setData).catch((e: Error) => {
      if (e.name !== "AbortError") setError(e.message);
    });
    return () => ctrl.abort();
  }, [attempt]);
  if (error) return <ErrorBox message={error} onRetry={() => setAttempt((a) => a + 1)} />;
  if (!data) return <Loading label="Chargement des sources…" />;
  const loaded = data.filter((s) => s.last_import);
  return (
    <ul className="divide-y divide-ink/10 border-y border-ink/10">
      {loaded.map((s) => (
        <li key={s.code} className="grid gap-1 py-4 md:grid-cols-[1fr_auto] md:gap-6">
          <div>
            <p className="font-semibold">{s.url ? <a href={s.url} target="_blank" rel="noreferrer" className="hover:underline">{s.name}</a> : s.name}</p>
            <p className="text-sm text-muted">{s.license}{s.notes ? `. ${s.notes}` : ""}</p>
          </div>
          <div className="flex items-start gap-3 text-xs text-muted md:flex-col md:items-end">
            <Stamp status={s.default_data_status} />
            {s.last_import?.version_date && <span>version du {day(s.last_import.version_date)}</span>}
            {s.last_import?.method === "manual_transcription" && <span>échantillon saisi manuellement</span>}
          </div>
        </li>
      ))}
    </ul>
  );
}
