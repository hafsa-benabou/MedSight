"use client";
import { Camera, CheckCircle2, CircleAlert, CircleHelp, ImageUp, Loader2, MessageCircleQuestion, RotateCcw, ScanLine, XCircle } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { SourceStamp } from "@/components/Stamp";
import { ErrorBox } from "@/components/States";
import { postFile, type IdentifyResponse, type IdentifyStatus, type PillCandidate } from "@/lib/api";
import { mad } from "@/lib/format";

const ACCEPTED = ["image/jpeg", "image/png", "image/webp"];
const MAX_MB = 8;

const STATUS: Record<IdentifyStatus, { label: string; tone: string; Icon: typeof CheckCircle2 }> = {
  identified: { label: "Identifié", tone: "border-health bg-mint text-[#0E5F51]", Icon: CheckCircle2 },
  ambiguous: { label: "Plusieurs possibilités", tone: "border-clinic/50 bg-white text-ink", Icon: CircleHelp },
  contradictory: { label: "Indices contradictoires", tone: "border-alert/40 bg-alert-soft text-alert", Icon: CircleAlert },
  not_found: { label: "Aucune correspondance", tone: "border-ink/20 bg-white text-ink", Icon: XCircle },
  unreadable: { label: "Photo illisible", tone: "border-sim/40 bg-sim-soft text-[#6B3E00]", Icon: CircleAlert },
  ocr_unavailable: { label: "Lecture du texte indisponible", tone: "border-sim/40 bg-sim-soft text-[#6B3E00]", Icon: CircleAlert },
};
const EVIDENCE: Record<string, string> = { match: "concordant", conflict: "contradictoire", unknown: "non lu" };
const RELIABILITY: Record<string, string> = { high: "élevée", medium: "moyenne", low: "faible", none: "aucune" };

export default function Identifier() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<IdentifyResponse | null>(null);
  const [camera, setCamera] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const stopCamera = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setCamera(false);
  }, []);
  useEffect(() => () => stopCamera(), [stopCamera]);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  function choose(f: File | null | undefined) {
    setError(null);
    setResult(null);
    if (!f) return;
    if (!ACCEPTED.includes(f.type)) { setError("Format non accepté : utilisez une photo JPEG, PNG ou WEBP."); return; }
    if (f.size > MAX_MB * 1024 * 1024) { setError(`Photo trop lourde (maximum ${MAX_MB} Mo).`); return; }
    setFile(f);
    setPreview(URL.createObjectURL(f));
  }

  async function openCamera() {
    setError(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      inputRef.current?.click();  // mobile : le sélecteur propose l'appareil photo (attribut capture)
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
      streamRef.current = stream;
      setCamera(true);
      requestAnimationFrame(() => { if (videoRef.current) { videoRef.current.srcObject = stream; void videoRef.current.play(); } });
    } catch {
      setError("Caméra inaccessible (autorisation refusée ou aucun appareil). Importez une photo à la place.");
    }
  }

  function capture() {
    const v = videoRef.current;
    if (!v || !v.videoWidth) return;
    const canvas = document.createElement("canvas");
    canvas.width = v.videoWidth;
    canvas.height = v.videoHeight;
    canvas.getContext("2d")?.drawImage(v, 0, 0);
    canvas.toBlob((blob) => {
      if (blob) choose(new File([blob], "capture.jpg", { type: "image/jpeg" }));
      stopCamera();
    }, "image/jpeg", 0.92);
  }

  async function analyse() {
    if (!file) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await postFile<IdentifyResponse>("/api/pills/identify", file, file.name));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setFile(null);
    setPreview(null);
    setResult(null);
    setError(null);
  }

  return (
    <div className="mt-10 grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)]">
      <section aria-labelledby="photo-title" className="rounded-2xl border border-ink/10 bg-white p-5 md:p-6">
        <h2 id="photo-title" className="text-lg font-semibold">1. Photo de la boîte</h2>
        {camera ? (
          <div className="mt-4">
            <video ref={videoRef} playsInline muted className="aspect-[4/3] w-full rounded-xl bg-ink object-cover" aria-label="Aperçu de la caméra" />
            <div className="mt-3 flex gap-2">
              <button onClick={capture} className="flex-1 rounded-lg bg-ink px-4 py-2.5 font-semibold text-white">Prendre la photo</button>
              <button onClick={stopCamera} className="rounded-lg border border-ink/20 px-4 py-2.5 font-semibold">Annuler</button>
            </div>
          </div>
        ) : (
          <label
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); choose(e.dataTransfer.files?.[0]); }}
            className={`mt-4 flex min-h-[15rem] cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-4 text-center transition-colors ${drag ? "border-health bg-mint" : "border-ink/20 hover:border-clinic"}`}>
            {preview ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={preview} alt="Photo sélectionnée" className="max-h-72 rounded-lg object-contain" />
            ) : (
              <>
                <ImageUp aria-hidden className="h-10 w-10 text-clinic" />
                <span className="mt-3 font-semibold">Glissez une photo ici ou cliquez pour choisir</span>
                <span className="mt-1 text-sm text-muted">JPEG, PNG ou WEBP, {MAX_MB} Mo maximum</span>
              </>
            )}
            <input ref={inputRef} type="file" accept={ACCEPTED.join(",")} capture="environment" className="sr-only"
              onChange={(e) => { choose(e.target.files?.[0]); e.target.value = ""; }} />
          </label>
        )}
        <div className="mt-4 flex flex-wrap gap-2">
          <button onClick={analyse} disabled={!file || busy}
            className="inline-flex items-center gap-2 rounded-lg bg-clinic px-5 py-2.5 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">
            {busy ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <ScanLine aria-hidden className="h-4 w-4" />}
            {busy ? "Analyse en cours…" : "Analyser la photo"}
          </button>
          {!camera && (
            <button onClick={openCamera} className="inline-flex items-center gap-2 rounded-lg border border-ink/20 px-4 py-2.5 font-semibold">
              <Camera aria-hidden className="h-4 w-4" /> Caméra
            </button>
          )}
          {file && !busy && (
            <button onClick={reset} className="inline-flex items-center gap-2 rounded-lg px-3 py-2.5 text-sm text-muted hover:text-ink">
              <RotateCcw aria-hidden className="h-4 w-4" /> Recommencer
            </button>
          )}
        </div>
        <ul className="mt-6 space-y-1.5 text-sm text-muted">
          <li>• Cadrez la face portant le nom et le dosage, ou le code-barres.</li>
          <li>• Évitez les reflets et le flou ; une lumière naturelle suffit.</li>
          <li>• La photo n&apos;est pas conservée et ne quitte pas le serveur MEDISIGHT.</li>
        </ul>
      </section>

      <section aria-labelledby="result-title" aria-live="polite" aria-busy={busy}>
        <h2 id="result-title" className="text-lg font-semibold">2. Résultat</h2>
        {error && <ErrorBox message={error} onRetry={file ? analyse : undefined} />}
        {busy && <ResultSkeleton />}
        {!busy && !error && !result && (
          <p className="mt-4 rounded-xl border border-ink/10 bg-white p-6 text-sm text-muted">
            Les correspondances apparaîtront ici, avec leur niveau de fiabilité et l&apos;explication de chaque indice.
          </p>
        )}
        {result && <Result data={result} />}
      </section>
    </div>
  );
}

function ResultSkeleton() {
  return (
    <div role="status" className="mt-4 space-y-3">
      <span className="sr-only">Analyse en cours : lecture du code-barres, OCR puis recherche dans le catalogue…</span>
      {[0, 1].map((i) => <div key={i} className="h-28 animate-pulse rounded-xl bg-ink/[0.06] motion-reduce:animate-none" />)}
    </div>
  );
}

function Result({ data }: { data: IdentifyResponse }) {
  const st = STATUS[data.status];
  return (
    <div className="mt-4 space-y-4">
      <div className={`rounded-xl border p-4 ${st.tone}`}>
        <p className="flex items-center gap-2 font-semibold"><st.Icon aria-hidden className="h-5 w-5" />{st.label}
          {data.reliability !== "none" && <span className="font-normal">— fiabilité {RELIABILITY[data.reliability] ?? data.reliability}</span>}</p>
        <p className="mt-1 text-sm">{data.message}</p>
        {data.reasons.length > 0 && <ul className="mt-2 list-disc pl-5 text-sm">{data.reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
      </div>

      {data.available_dosages.length > 0 && (
        <p className="rounded-lg border border-ink/10 bg-white px-4 py-3 text-sm">
          Dosages référencés pour ce nom : <strong>{data.available_dosages.join(", ")}</strong>. Le dosage lu n&apos;a pas été remplacé.
        </p>
      )}

      {data.candidates.map((c) => <CandidateCard key={c.presentation_id} c={c} />)}

      <details className="rounded-xl border border-ink/10 bg-white p-4 text-sm">
        <summary className="cursor-pointer font-semibold">Ce que MEDISIGHT a lu</summary>
        <dl className="mt-3 grid gap-x-6 gap-y-2 sm:grid-cols-[10rem_1fr]">
          <dt className="text-muted">Code-barres</dt>
          <dd>{data.barcodes.length ? data.barcodes.map((b) => `${b.code ?? "?"} (${b.format}, ${b.status}${b.in_catalog ? ", présent au catalogue" : ""})`).join(" ; ") : "aucun lu"}</dd>
          <dt className="text-muted">OCR</dt>
          <dd>{data.ocr.available ? `${data.ocr.engine} ${data.ocr.version ?? ""} (${data.ocr.languages})${data.ocr.mean_confidence != null ? `, confiance moyenne ${data.ocr.mean_confidence}` : ""}` : "indisponible sur ce serveur"}</dd>
          <dt className="text-muted">Nom(s) candidat(s)</dt><dd>{data.extracted.brand_segments.join(", ") || "—"}</dd>
          <dt className="text-muted">Dosage lu</dt><dd>{data.extracted.dosage_text ?? (data.extracted.doses.map((d) => d.text).join(", ") || "—")}</dd>
          <dt className="text-muted">Substance(s)</dt><dd>{data.extracted.substances.map((s) => s.name).join(", ") || "—"}</dd>
          <dt className="text-muted">Qualité photo</dt><dd>{data.quality.usable ? "exploitable" : `insuffisante (${data.quality.issues.join(", ")})`}</dd>
          <dt className="text-muted">Durée</dt><dd>{data.timings_ms.total_ms} ms</dd>
        </dl>
        {data.ocr.lines.length > 0 && (
          <ul className="mt-3 max-h-40 overflow-auto rounded bg-paper p-2 font-mono text-xs" dir="auto">
            {data.ocr.lines.map((l, i) => <li key={i}>{l.text} <span className="text-muted">({l.confidence})</span></li>)}
          </ul>
        )}
      </details>

      {data.warnings.length > 0 && (
        <ul className="space-y-1 text-xs text-muted">{data.warnings.map((w) => <li key={w}>⚠ {w}</li>)}</ul>
      )}
      <p className="text-xs text-muted">{data.score_note} {data.disclaimer}</p>
    </div>
  );
}

function CandidateCard({ c }: { c: PillCandidate }) {
  const sim = c.data_status === "simulated";
  return (
    <article className="overflow-hidden rounded-xl border border-ink/15 bg-white">
      <div className={`h-1.5 ${sim ? "bg-sim" : "bg-health"}`} />
      <div className="p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs text-muted">Candidat n° {c.rank}</p>
            <h3><span className="display text-2xl">{c.brand}</span> <span className="label-wide text-clinic">{c.dosage}</span></h3>
            <p className="text-sm text-muted">{c.form}{c.laboratory ? `, ${c.laboratory}` : ""} — {c.presentation}</p>
          </div>
          <div className="text-right">
            <p className="display text-2xl" aria-label={`Indice de correspondance ${c.score} sur 100`}>{Math.round(c.score)}<span className="text-sm text-muted">/100</span></p>
            <div className="mt-1 h-1.5 w-24 rounded bg-ink/10"><div className="h-1.5 rounded bg-health" style={{ width: `${c.score}%` }} /></div>
          </div>
        </div>
        <p className="mt-2 text-sm"><span className="font-semibold">Composition : </span>{c.ingredients.map((i) => `${i.name}${i.strength ? ` ${i.strength}` : ""}`).join(" + ") || "non renseignée"}</p>
        <p className="mt-1 text-sm"><span className="font-semibold">PPV : </span>{mad(c.ppv)}{sim && c.ppv != null ? " (prix fictif, démonstration)" : ""}{c.ean13 ? <span className="text-muted"> · EAN {c.ean13}</span> : null}</p>
        <ul className="mt-3 flex flex-wrap gap-1.5 text-xs">
          {(["barcode", "dosage", "substance", "form", "pack"] as const).map((k) => (
            <li key={k} className={`rounded border px-1.5 py-0.5 ${c.evidence[k] === "match" ? "border-health text-[#0E7563]" : c.evidence[k] === "conflict" ? "border-alert text-alert" : "border-ink/15 text-muted"}`}>
              {({ barcode: "Code-barres", dosage: "Dosage", substance: "Substance", form: "Forme", pack: "Boîte" })[k]} : {EVIDENCE[c.evidence[k]] ?? c.evidence[k]}
            </li>
          ))}
          {c.evidence.brand_similarity > 0 && <li className="rounded border border-ink/15 px-1.5 py-0.5 text-muted">Nom : {Math.round(c.evidence.brand_similarity)}/100</li>}
        </ul>
        <details className="mt-2 text-sm">
          <summary className="cursor-pointer text-clinic">Pourquoi ce candidat ?</summary>
          <ul className="mt-1 list-disc pl-5 text-muted">{c.explanation.map((e) => <li key={e}>{e}</li>)}</ul>
        </details>
        <div className="mt-3"><SourceStamp status={c.data_status} source={c.source} date={c.price_as_of} /></div>
        <div className="mt-4 flex flex-wrap gap-2 text-sm">
          <Link href={`/medicines/${c.medicine_id}`} className="rounded-lg border border-ink/20 px-3 py-2 font-semibold hover:border-ink">Voir la fiche</Link>
          <Link href={`/chat?medicine=${c.medicine_id}`} className="inline-flex items-center gap-1.5 rounded-lg bg-ink px-3 py-2 font-semibold text-white hover:bg-[#0d2f4b]">
            <MessageCircleQuestion aria-hidden className="h-4 w-4" /> Poser une question
          </Link>
        </div>
      </div>
    </article>
  );
}
