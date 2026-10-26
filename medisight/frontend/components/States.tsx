export function Loading({ label = "Chargement…" }: { label?: string }) {
  return <p role="status" aria-live="polite" className="py-10 text-sm text-muted">{label}</p>;
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="my-6 rounded-lg border border-alert/30 bg-alert-soft p-4 text-sm text-alert">
      <p>{message}</p>
      {onRetry && <button onClick={onRetry} className="mt-3 rounded-md border border-alert/40 bg-white px-3 py-1.5 font-semibold">Réessayer</button>}
    </div>
  );
}

export function Notice({ children, tone = "info" }: { children: React.ReactNode; tone?: "info" | "sim" }) {
  const cls = tone === "sim" ? "border-sim/40 bg-sim-soft text-[#6B3E00]" : "border-clinic/30 bg-white text-ink";
  return <div className={`rounded-lg border px-4 py-3 text-sm ${cls}`}>{children}</div>;
}
