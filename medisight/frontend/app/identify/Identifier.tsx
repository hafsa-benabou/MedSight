"use client";
import type { LucideIcon } from "lucide-react";
import { ArrowRight, Barcode, Camera, CheckCircle2, CircleAlert, CircleHelp, Cpu, Database, ImageUp, Loader2, MessageCircleQuestion, ScanLine,
  ScanText, ShieldCheck, Trash2, TriangleAlert, XCircle } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { CARD } from "@/components/PageShell";
import { SourceStamp } from "@/components/Stamp";
import { ErrorBox } from "@/components/States";
import { postFile, type IdentifyResponse, type IdentifyStatus, type PillCandidate } from "@/lib/api";
import { mad } from "@/lib/format";

const ACCEPTED = ["image/jpeg", "image/png", "image/webp"];
const MAX_MB = 8;  // MAX_UPLOAD_MB du backend (app/core/config.py, .env)
const DISCLAIMER = "L'identification visuelle est une hypothèse à confirmer auprès d'un professionnel de santé.";

const STATUS: Record<IdentifyStatus, { label: string; tone: string; Icon: LucideIcon }> = {
  identified: { label: "Correspondance avec des indices concordants", tone: "border-health/40 bg-mint text-[#0E5F51]", Icon: CheckCircle2 },
  ambiguous: { label: "Plusieurs correspondances possibles", tone: "border-clinic/30 bg-[#E6F1F7] text-ink", Icon: CircleHelp },
  contradictory: { label: "Informations contradictoires", tone: "border-alert/30 bg-alert-soft text-alert", Icon: CircleAlert },
  not_found: { label: "Médicament introuvable dans le catalogue", tone: "border-ink/15 bg-paper text-ink", Icon: XCircle },
  unreadable: { label: "Image illisible", tone: "border-sim/40 bg-sim-soft text-[#6B3E00]", Icon: CircleAlert },
  ocr_unavailable: { label: "Lecture du texte (OCR) indisponible", tone: "border-sim/40 bg-sim-soft text-[#6B3E00]", Icon: CircleAlert },
};
// Couleur du bandeau selon la lecture prudente du backend (nature des indices, pas le seul score) :
// vert = présentation étayée par des indices indépendants ; orange = candidat ou plusieurs possibilités ; rouge = échec
const VERDICT_TONE = {
  confirmed: "border-health/40 bg-mint text-[#0E5F51]",
  partial: "border-sim/40 bg-sim-soft text-[#6B3E00]",
  failed: "border-alert/30 bg-alert-soft text-alert",
} as const;
function banner(data: IdentifyResponse): { label: string; tone: string; Icon: LucideIcon } {
  const st = STATUS[data.status];
  const verdict = data.verdict ?? (data.status === "identified" ? "partial" : data.status === "ambiguous" ? "partial" : "failed");
  if (data.status === "identified" && verdict !== "confirmed")
    return { label: "Médicament candidat reconnu — présentation exacte non confirmée", tone: VERDICT_TONE.partial, Icon: CircleHelp };
  return { ...st, tone: VERDICT_TONE[verdict] };
}
const EVIDENCE: Record<string, string> = { match: "concordant", conflict: "contradictoire", unknown: "non lu" };
const RELIABILITY: Record<string, string> = { high: "élevée", medium: "moyenne", low: "faible", none: "aucune" };
// Étapes du pipeline ; leur durée n'est affichée qu'à partir des mesures renvoyées par le serveur
const STEPS: [string, LucideIcon, string][] = [
  ["decode_ms", ImageUp, "Prétraitement de l'image"],
  ["quality_barcode_ms", Barcode, "Qualité et lecture du code-barres"],
  ["ocr_ms", ScanText, "Lecture du texte imprimé (OCR)"],
  ["match_ms", Database, "Recherche dans le catalogue PostgreSQL"],
];

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
  const captureRef = useRef<HTMLInputElement>(null);
  const resultRef = useRef<HTMLElement>(null);

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
      captureRef.current?.click();  // mobile : le sélecteur propose l'appareil photo (attribut capture)
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
    if (!file || busy) return;
    setBusy(true);
    setError(null);
    setResult(null);
    // Sur mobile, la colonne des résultats est sous l'image : elle est ramenée dans la vue
    if (window.matchMedia("(max-width: 1023px)").matches) resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
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

  const pick = () => inputRef.current?.click();

  return (
    <div className="mt-8 grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
      <section aria-labelledby="photo-title" className={`${CARD} p-5 md:p-6`}>
        <div className="flex items-center gap-3">
          <span aria-hidden className="grid h-10 w-10 place-items-center rounded-xl bg-mint text-[#11806B]"><ScanLine size={20} /></span>
          <div>
            <h2 id="photo-title" className="font-semibold text-ink">Photo de la boîte</h2>
            <p className="text-xs text-muted">Face portant le nom, le dosage ou le code-barres</p>
          </div>
        </div>

        {camera ? (
          <div className="mt-5">
            <video ref={videoRef} playsInline muted className="aspect-[4/3] w-full rounded-xl bg-ink object-cover" aria-label="Aperçu de la caméra" />
            <div className="mt-3 flex gap-2">
              <button onClick={capture} className="inline-flex min-h-11 flex-1 items-center justify-center gap-2 rounded-xl bg-ink px-4 font-semibold text-white transition hover:bg-[#0d2f4b]">
                <Camera aria-hidden className="h-4 w-4" /> Prendre la photo
              </button>
              <button onClick={stopCamera} className="min-h-11 rounded-xl border border-ink/15 px-4 font-semibold transition hover:border-ink">Annuler</button>
            </div>
          </div>
        ) : (
          <div
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); choose(e.dataTransfer.files?.[0]); }}
            onClick={() => { if (!preview) pick(); }}
            className={`mt-5 flex min-h-[17rem] flex-col items-center justify-center rounded-xl border-2 border-dashed p-5 text-center transition
              ${preview ? "border-ink/10 bg-paper/60" : "cursor-pointer"} ${drag ? "border-health bg-mint" : preview ? "" : "border-ink/15 bg-paper/40 hover:border-health/60 hover:bg-mint/40"}`}>
            {preview ? (
              <>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={preview} alt="Photo sélectionnée" className="max-h-72 rounded-lg object-contain shadow-sm" />
                <p className="mt-3 max-w-full truncate text-xs text-muted">{file?.name} · {file ? (file.size / 1024 / 1024).toFixed(1) : 0} Mo</p>
                <div className="mt-3 flex flex-wrap justify-center gap-2">
                  <button type="button" onClick={pick} disabled={busy}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-ink/15 bg-white px-3 py-2 text-sm font-semibold transition hover:border-ink disabled:opacity-50">
                    <ImageUp aria-hidden className="h-4 w-4" /> Remplacer
                  </button>
                  <button type="button" onClick={reset} disabled={busy}
                    className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-semibold text-muted transition hover:bg-alert-soft hover:text-alert disabled:opacity-50">
                    <Trash2 aria-hidden className="h-4 w-4" /> Retirer
                  </button>
                </div>
              </>
            ) : (
              <>
                <span aria-hidden className="grid h-16 w-16 place-items-center rounded-2xl bg-white text-[#11806B] shadow-[0_8px_24px_-14px_rgba(18,59,93,0.35)]"><ScanLine size={30} /></span>
                <p className="mt-4 font-semibold text-ink">Glissez-déposez la photo de votre boîte ici</p>
                <p className="mt-1 text-xs text-muted">JPEG, PNG ou WEBP · {MAX_MB} Mo maximum</p>
                <div className="mt-5 flex flex-col gap-2 sm:flex-row">
                  <button type="button" onClick={(e) => { e.stopPropagation(); pick(); }}
                    className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-ink px-5 text-sm font-semibold text-white transition hover:bg-[#0d2f4b]">
                    <ImageUp aria-hidden className="h-4 w-4" /> Importer une photo
                  </button>
                  <button type="button" onClick={(e) => { e.stopPropagation(); void openCamera(); }}
                    className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-ink/15 bg-white px-5 text-sm font-semibold transition hover:border-ink">
                    <Camera aria-hidden className="h-4 w-4" /> Utiliser la caméra
                  </button>
                </div>
              </>
            )}
          </div>
        )}
        <input ref={inputRef} type="file" accept={ACCEPTED.join(",")} className="sr-only" tabIndex={-1} aria-hidden
          onChange={(e) => { choose(e.target.files?.[0]); e.target.value = ""; }} />
        <input ref={captureRef} type="file" accept={ACCEPTED.join(",")} capture="environment" className="sr-only" tabIndex={-1} aria-hidden
          onChange={(e) => { choose(e.target.files?.[0]); e.target.value = ""; }} />

        <button onClick={analyse} disabled={!file || busy}
          className="mt-5 inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-xl bg-[#11806B] px-6 font-semibold text-white shadow-[0_8px_20px_-10px_rgba(17,128,107,0.6)] transition hover:bg-[#0c6a58] disabled:cursor-not-allowed disabled:bg-ink/25 disabled:shadow-none">
          {busy ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <ScanLine aria-hidden className="h-4 w-4" />}
          {busy ? "Analyse en cours…" : "Analyser le médicament"}
        </button>

        <ul className="mt-5 space-y-2 text-xs leading-relaxed text-muted">
          <li className="flex gap-2"><span aria-hidden className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-health" />Cadrez la face portant le nom et le dosage, ou le code-barres.</li>
          <li className="flex gap-2"><span aria-hidden className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-health" />Évitez les reflets et le flou ; une lumière naturelle suffit.</li>
          <li className="flex gap-2"><span aria-hidden className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-health" />La photo n&apos;est pas conservée et ne quitte pas le serveur MedSight.</li>
        </ul>
      </section>

      <section ref={resultRef} aria-labelledby="result-title" aria-live="polite" aria-busy={busy} className={`${CARD} scroll-mt-20 p-5 md:p-6`}>
        <div className="flex items-center gap-3">
          <span aria-hidden className="grid h-10 w-10 place-items-center rounded-xl bg-[#E6F1F7] text-clinic"><Cpu size={20} /></span>
          <h2 id="result-title" className="font-semibold text-ink">Résultat de l&apos;analyse</h2>
        </div>
        {error && <ErrorBox message={error} onRetry={file ? analyse : undefined} />}
        {busy && <Analysing />}
        {!busy && !error && !result && (
          <div className="flex flex-col items-center px-4 py-14 text-center">
            <span aria-hidden className="grid h-16 w-16 place-items-center rounded-2xl bg-paper text-muted/60"><ScanText size={30} /></span>
            <p className="mt-4 max-w-xs text-sm text-muted">Votre résultat apparaîtra ici après l&apos;analyse de l&apos;image.</p>
          </div>
        )}
        {result && <Result data={result} />}
        <p className="mt-6 flex gap-2 border-t border-ink/10 pt-4 text-xs leading-relaxed text-muted">
          <ShieldCheck aria-hidden className="mt-px h-4 w-4 shrink-0 text-clinic" />{DISCLAIMER}
        </p>
      </section>
    </div>
  );
}

/** Pendant l'analyse : les étapes sont présentées sans aucun état d'avancement simulé. */
function Analysing() {
  return (
    <div role="status" className="py-8">
      <p className="flex items-center gap-3 text-sm font-semibold text-ink">
        <span aria-hidden className="flex gap-1"><i className="typing-dot" /><i className="typing-dot" /><i className="typing-dot" /></span>
        Analyse de votre image en cours...
      </p>
      <p className="mt-4 text-xs text-muted">Étapes réalisées par le serveur :</p>
      <ol className="mt-2 space-y-2">
        {STEPS.map(([k, Icon, label]) => (
          <li key={k} className="flex items-center gap-3 rounded-lg bg-paper px-3 py-2.5 text-sm text-muted">
            <Icon aria-hidden className="h-4 w-4 shrink-0 text-clinic" />{label}
          </li>
        ))}
      </ol>
    </div>
  );
}

function Result({ data }: { data: IdentifyResponse }) {
  const st = banner(data);
  const timed = STEPS.filter(([k]) => data.timings_ms[k] != null);
  const ex = data.extracted;
  const tied = data.status === "identified" && data.identified_level === "medicine" && data.candidates.length > 1;
  return (
    <div className="msg-in mt-5 space-y-4">
      <div className={`rounded-xl border p-4 ${st.tone}`}>
        <p className="flex items-start gap-2 font-semibold"><st.Icon aria-hidden className="mt-0.5 h-5 w-5 shrink-0" />
          <span>{st.label}{data.reliability !== "none" && <span className="font-normal"> · fiabilité {RELIABILITY[data.reliability] ?? data.reliability}</span>}</span></p>
        <p className="mt-1.5 text-sm">{data.message}</p>
        {data.reasons.length > 0 && <ul className="mt-2 list-disc space-y-0.5 pl-5 text-sm">{data.reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
      </div>

      {data.available_dosages.length > 0 && (
        <p className="rounded-xl border border-ink/10 bg-paper px-4 py-3 text-sm">
          Dosages référencés pour ce nom : <strong>{data.available_dosages.join(", ")}</strong>. Le dosage lu n&apos;a pas été remplacé.
        </p>
      )}

      {data.candidates.length > 1 && <p className="text-xs font-semibold uppercase tracking-[0.08em] text-muted">{tied
        ? `${data.candidates.length} présentations possibles à égalité — aucune n'est retenue à la place des autres`
        : `${data.candidates.length} candidats, du plus au moins concordant`}</p>}
      {data.candidates.map((c) => <CandidateCard key={c.presentation_id} c={c} barcodes={data.barcodes.map((b) => b.code).filter(Boolean) as string[]} />)}

      <details className="rounded-xl border border-ink/10 bg-white p-4 text-sm">
        <summary className="cursor-pointer select-none font-semibold text-ink">Ce que MedSight a lu sur la photo</summary>
        <p className="mt-2 text-xs text-muted">Informations détectées sur la photo uniquement : aucune n&apos;est complétée par le catalogue. « — » signifie non lu.</p>
        <dl className="mt-3 grid gap-x-6 gap-y-2 sm:grid-cols-[9.5rem_minmax(0,1fr)]">
          <dt className="text-muted">Code-barres lu</dt>
          <dd className="break-words">{data.barcodes.length ? data.barcodes.map((b) => `${b.code ?? "?"} (${b.format}, ${b.status}${b.in_catalog ? ", présent au catalogue" : ""})`).join(" ; ") : "aucun code-barres lu sur la photo"}</dd>
          <dt className="text-muted">OCR</dt>
          <dd>{data.ocr.available ? `${data.ocr.engine} ${data.ocr.version ?? ""} (${data.ocr.languages})${data.ocr.mean_confidence != null ? `, confiance moyenne ${data.ocr.mean_confidence}` : ""}` : "indisponible sur ce serveur"}</dd>
          <dt className="text-muted">Nom(s) candidat(s)</dt><dd>{data.extracted.brand_segments.join(", ") || "—"}</dd>
          <dt className="text-muted">Dosage lu</dt><dd>{data.extracted.dosage_text ?? (data.extracted.doses.map((d) => d.text).join(", ") || "—")}</dd>
          <dt className="text-muted">Substance(s)</dt><dd>{data.extracted.substances.map((s) => s.name).join(", ") || "—"}</dd>
          <dt className="text-muted">Forme lue</dt><dd>{ex.form_text ?? ex.form ?? "—"}</dd>
          <dt className="text-muted">Conditionnement lu</dt><dd>{ex.pack_text ?? (ex.pack_quantity != null ? String(ex.pack_quantity) : "—")}</dd>
          <dt className="text-muted">Laboratoire lu</dt><dd>{ex.laboratory ?? "—"}</dd>
          <dt className="text-muted">Qualité photo</dt><dd>{data.quality.usable ? "exploitable" : `insuffisante (${data.quality.issues.join(", ")})`}</dd>
        </dl>
        {timed.length > 0 && (
          <ol className="mt-4 grid gap-1.5 sm:grid-cols-2">
            {timed.map(([k, Icon, label]) => (
              <li key={k} className="flex items-center gap-2 rounded-lg bg-paper px-3 py-2 text-xs">
                <Icon aria-hidden className="h-3.5 w-3.5 shrink-0 text-clinic" /><span className="flex-1">{label}</span><span className="tabular-nums text-muted">{data.timings_ms[k]} ms</span>
              </li>
            ))}
          </ol>
        )}
        {data.timings_ms.total_ms != null && <p className="mt-2 text-xs text-muted">Durée totale mesurée : {data.timings_ms.total_ms} ms</p>}
        {data.ocr.lines.length > 0 && (
          <ul className="mt-3 max-h-40 overflow-auto rounded-lg bg-paper p-2 font-mono text-xs" dir="auto">
            {data.ocr.lines.map((l, i) => <li key={i}>{l.text} <span className="text-muted">({l.confidence})</span></li>)}
          </ul>
        )}
      </details>

      {data.warnings.length > 0 && (
        <ul className="space-y-1">{data.warnings.map((w) => (
          <li key={w} className="flex gap-1.5 text-xs text-[#6B3E00]"><TriangleAlert aria-hidden className="mt-px h-3.5 w-3.5 shrink-0" />{w}</li>))}
        </ul>
      )}
      <p className="text-xs leading-relaxed text-muted">{data.score_note} {data.disclaimer}</p>
    </div>
  );
}

function CandidateCard({ c, barcodes }: { c: PillCandidate; barcodes: string[] }) {
  const sim = c.data_status === "simulated";
  const rows: [string, string | null][] = [
    ["Substance active", c.ingredients.map((i) => `${i.name}${i.strength ? ` ${i.strength}` : ""}`).join(" + ") || null],
    ["Forme", c.form],
    ["Laboratoire", c.laboratory],
    ["Présentation", c.presentation],
    ["Code-barres", c.ean13 ? `${c.ean13} ${barcodes.includes(c.ean13) ? "(fiche ; identique au code lu sur la photo)" : "(fiche ; non lu sur la photo)"}` : null],
    ["Prix (PPV)", c.ppv != null ? `${mad(c.ppv)}${sim ? " (prix fictif, démonstration)" : ""}` : null],
  ];
  return (
    <article className="overflow-hidden rounded-xl border border-ink/10 bg-white shadow-[0_6px_18px_-14px_rgba(18,59,93,0.3)]">
      <div className={`h-1 ${sim ? "bg-sim" : "bg-gradient-to-r from-clinic to-health"}`} />
      <div className="p-4 md:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">Candidat n° {c.rank}</p>
            <h3 className="mt-0.5" dir="ltr"><span className="display text-xl md:text-2xl">{c.brand}</span>{c.dosage && <span className="ml-2 font-semibold text-clinic">{c.dosage}</span>}</h3>
            <p className="mt-0.5 text-sm font-semibold text-ink">{c.presentation}</p>
          </div>
          <div className="text-right" aria-label={`Indice de correspondance ${Math.round(c.score)} sur 100`}>
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">Correspondance</p>
            <p className="display text-2xl leading-tight">{Math.round(c.score)}<span className="text-sm text-muted">/100</span></p>
            <div className="ml-auto mt-1 h-1.5 w-24 rounded-full bg-ink/10"><div className="h-1.5 rounded-full bg-health" style={{ width: `${Math.min(100, c.score)}%` }} /></div>
          </div>
        </div>
        <p className="mt-4 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">Informations issues du catalogue</p>
        <dl className="mt-1.5 space-y-1.5 text-sm">
          {rows.map(([k, v]) => (
            <div key={k} className="grid grid-cols-[7rem_minmax(0,1fr)] gap-2 sm:grid-cols-[8rem_minmax(0,1fr)]">
              <dt className="text-muted">{k}</dt>
              <dd className={`break-words ${v ? "" : "text-muted"}`}>{v ?? (k === "Prix (PPV)" ? "Prix non disponible" : "Non renseigné")}</dd>
            </div>
          ))}
        </dl>
        <ul className="mt-4 flex flex-wrap gap-1.5 text-xs" aria-label="Indices comparés">
          {(["barcode", "dosage", "substance", "form", "pack"] as const).map((k) => (
            <li key={k} className={`rounded-full border px-2 py-0.5 ${c.evidence[k] === "match" ? "border-health/60 bg-mint/60 text-[#0E7563]" : c.evidence[k] === "conflict" ? "border-alert/50 bg-alert-soft text-alert" : "border-ink/15 text-muted"}`}>
              {({ barcode: "Code-barres", dosage: "Dosage", substance: "Substance", form: "Forme", pack: "Boîte" })[k]} : {EVIDENCE[c.evidence[k]] ?? c.evidence[k]}
            </li>
          ))}
          {c.evidence.brand_similarity > 0 && <li className="rounded-full border border-ink/15 px-2 py-0.5 text-muted">Nom : {Math.round(c.evidence.brand_similarity)}/100</li>}
          {c.evidence.laboratory && c.evidence.laboratory !== "unknown" && (
            <li className={`rounded-full border px-2 py-0.5 ${c.evidence.laboratory === "match" ? "border-health/60 bg-mint/60 text-[#0E7563]" : "border-sim/40 bg-sim-soft text-[#6B3E00]"}`}>
              Laboratoire : {c.evidence.laboratory === "match" ? "concordant" : "différent (à vérifier)"}
            </li>
          )}
        </ul>
        <details className="mt-3 text-sm">
          <summary className="cursor-pointer select-none text-xs font-semibold text-clinic">Pourquoi ce candidat ?</summary>
          <ul className="mt-1.5 list-disc pl-5 text-muted">{c.explanation.map((e) => <li key={e}>{e}</li>)}</ul>
        </details>
        <div className="mt-3"><SourceStamp status={c.data_status} source={c.source} date={c.price_as_of} /></div>
        <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
          <Link href={`/medicines/${c.medicine_id}`}
            className="inline-flex min-h-10 items-center justify-center gap-1.5 rounded-lg border border-ink/15 px-4 text-sm font-semibold transition hover:border-ink">
            Consulter la fiche <ArrowRight aria-hidden className="h-3.5 w-3.5" />
          </Link>
          <Link href={`/chat?medicine=${c.medicine_id}`}
            className="inline-flex min-h-10 items-center justify-center gap-1.5 rounded-lg bg-ink px-4 text-sm font-semibold text-white transition hover:bg-[#0d2f4b]">
            <MessageCircleQuestion aria-hidden className="h-4 w-4" /> Poser une question à MedSight AI
          </Link>
        </div>
      </div>
    </article>
  );
}
