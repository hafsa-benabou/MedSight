"use client";
import { Bot, Loader2, Pill, SendHorizontal, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Stamp } from "@/components/Stamp";
import { api, postJson, type ChatResponse, type MedicineCard } from "@/lib/api";
import { mad } from "@/lib/format";

type Turn = { id: number; role: "user" | "assistant"; text: string; data?: ChatResponse; error?: boolean };

const DEFAULT_SUGGESTIONS = ["Ch7al taman dyal Doliprane 500mg ?", "Quels sont les génériques d'AMLOR 5 mg ?",
  "شنو المادة الفعالة ديال AMLOR؟", "Je cherche une pharmacie à Rabat", "Quels dosages existent pour AMLOR ?"];
const UNDERSTANDING: Record<string, string> = {
  understood: "compris", partial: "compris partiellement", ambiguous: "ambigu", not_found: "médicament introuvable",
  clarification_needed: "précision demandée", dosage_not_found: "dosage non référencé", information_unavailable: "information absente des sources",
  refused_medical_advice: "avis médical refusé", emergency: "urgence", not_understood: "non compris",
};
const LANG: Record<string, string> = { fr: "français", ar: "arabe", darija: "darija (arabe)", darija_latin: "darija (latin)", en: "anglais" };
const isArabic = (s: string) => /[؀-ۿ]/.test(s);

export default function Chat() {
  const params = useSearchParams();
  const router = useRouter();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [context, setContext] = useState<MedicineCard | null>(null);
  const [pendingContext, setPendingContext] = useState<number | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>(DEFAULT_SUGGESTIONS);
  const [contextError, setContextError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const nextId = useRef(1);

  // Contexte transmis par le Pill Identifier ou une fiche : identifiant PostgreSQL vérifié par l'API
  useEffect(() => {
    const raw = params.get("medicine");
    const id = raw && /^\d+$/.test(raw) ? Number(raw) : null;
    if (!id) return;
    const ctrl = new AbortController();
    api<{ medicine: MedicineCard; suggestions: string[] }>(`/api/chat/suggestions?medicine_id=${id}`, ctrl.signal)
      .then((d) => { setContext(d.medicine); setPendingContext(id); setSuggestions(d.suggestions); setContextError(null); })
      .catch((e: Error) => { if (e.name !== "AbortError") setContextError(`Médicament de contexte non chargé : ${e.message}`); });
    return () => ctrl.abort();
  }, [params]);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [turns, busy]);

  async function send(text: string) {
    const message = text.trim();
    if (!message || busy) return;
    setInput("");
    setTurns((t) => [...t, { id: nextId.current++, role: "user", text: message }]);
    setBusy(true);
    try {
      const data = await postJson<ChatResponse>("/api/chat", {
        message, conversation_id: conversationId, context_medicine_id: pendingContext ?? undefined });
      setConversationId(data.conversation_id);
      setPendingContext(null);
      if (data.context_medicine) setContext(data.context_medicine);
      if (data.suggestions.length) setSuggestions(data.suggestions);
      setTurns((t) => [...t, { id: nextId.current++, role: "assistant", text: data.message, data }]);
    } catch (e) {
      setTurns((t) => [...t, { id: nextId.current++, role: "assistant", text: (e as Error).message, error: true }]);
    } finally {
      setBusy(false);
    }
  }

  async function clear() {
    if (conversationId) await fetch(`/api/chat/${conversationId}`, { method: "DELETE" }).catch(() => undefined);
    setTurns([]);
    setConversationId(null);
    setContext(null);
    setPendingContext(null);
    setSuggestions(DEFAULT_SUGGESTIONS);
    router.replace("/chat");
  }

  return (
    <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_18rem]">
      <section aria-label="Conversation" className="flex min-h-[32rem] flex-col rounded-2xl border border-ink/10 bg-white">
        {context && (
          <div className="flex items-center gap-3 border-b border-ink/10 bg-mint/60 px-4 py-2.5 text-sm">
            <Pill aria-hidden className="h-4 w-4 shrink-0 text-health" />
            <p className="min-w-0 flex-1 truncate">Médicament de la conversation : <Link href={`/medicines/${context.id}`} className="font-semibold underline underline-offset-2">{context.brand} {context.dosage}</Link>
              {context.data_status === "simulated" && <span className="ml-2"><Stamp status="simulated" /></span>}</p>
            <button onClick={() => { setContext(null); setPendingContext(null); router.replace("/chat"); }} aria-label="Retirer le contexte" className="rounded p-1 hover:bg-white"><X className="h-4 w-4" /></button>
          </div>
        )}
        {contextError && <p role="alert" className="border-b border-alert/20 bg-alert-soft px-4 py-2 text-sm text-alert">{contextError}</p>}

        <ol className="flex-1 space-y-4 overflow-y-auto p-4 md:p-5" aria-live="polite">
          {turns.length === 0 && (
            <li className="mx-auto max-w-md py-10 text-center text-muted">
              <Bot aria-hidden className="mx-auto h-9 w-9 text-clinic" />
              <p className="mt-3">Exemple : « Quel est le prix d&apos;AMLOR 5 mg ? » ou « شنو المادة الفعالة ديال هاد الدوا؟ ».</p>
            </li>
          )}
          {turns.map((t) => <Message key={t.id} turn={t} onAsk={send} />)}
          {busy && (
            <li className="flex items-center gap-2 text-sm text-muted" role="status">
              <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> L&apos;assistant consulte la base…
            </li>
          )}
          <div ref={endRef} />
        </ol>

        <form onSubmit={(e) => { e.preventDefault(); void send(input); }} className="flex gap-2 border-t border-ink/10 p-3">
          <label htmlFor="chat-input" className="sr-only">Votre question</label>
          <input id="chat-input" value={input} onChange={(e) => setInput(e.target.value)} maxLength={1000} autoComplete="off"
            dir={isArabic(input) ? "rtl" : "auto"} placeholder="Votre question (français, العربية, darija)…"
            className="min-w-0 flex-1 rounded-lg border border-ink/20 px-3 py-2.5 focus:border-clinic focus:outline-none" />
          <button type="submit" disabled={busy || !input.trim()} aria-label="Envoyer"
            className="inline-flex items-center gap-2 rounded-lg bg-ink px-4 py-2.5 font-semibold text-white disabled:opacity-50">
            <SendHorizontal aria-hidden className="h-4 w-4" /><span className="hidden sm:inline">Envoyer</span>
          </button>
        </form>
      </section>

      <aside className="space-y-5">
        <div>
          <p className="text-sm font-semibold">Suggestions</p>
          <ul className="mt-2 flex flex-wrap gap-2 lg:flex-col">
            {suggestions.map((s) => (
              <li key={s}><button onClick={() => send(s)} disabled={busy} dir="auto"
                className="w-full rounded-lg border border-ink/15 bg-white px-3 py-2 text-left text-sm hover:border-clinic disabled:opacity-50">{s}</button></li>
            ))}
          </ul>
        </div>
        <div className="rounded-xl border border-ink/10 bg-white p-4 text-xs text-muted">
          <p className="font-semibold text-ink">Comment l&apos;assistant répond</p>
          <p className="mt-1">Analyse du message (langue, intention, médicament, dosage, ville), recherche dans PostgreSQL puis réponse rédigée à partir des données trouvées. Aucun modèle de langage externe n&apos;est utilisé.</p>
          <p className="mt-2">Votre texte n&apos;est pas conservé ; seule son analyse l&apos;est 72 h.</p>
        </div>
        {turns.length > 0 && (
          <button onClick={clear} className="inline-flex items-center gap-2 text-sm text-muted hover:text-alert">
            <Trash2 aria-hidden className="h-4 w-4" /> Effacer la conversation
          </button>
        )}
      </aside>
    </div>
  );
}

function Message({ turn, onAsk }: { turn: Turn; onAsk: (s: string) => void }) {
  const rtl = turn.role === "assistant" ? turn.data?.language.reply_language === "ar" : isArabic(turn.text);
  if (turn.role === "user") {
    return (
      <li className="flex justify-end">
        <p dir={rtl ? "rtl" : "auto"} className="max-w-[85%] whitespace-pre-line rounded-2xl rounded-br-sm bg-ink px-4 py-2.5 text-white">{turn.text}</p>
      </li>
    );
  }
  const d = turn.data;
  return (
    <li className="flex gap-2.5">
      <span aria-hidden className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-mint"><Bot className="h-4 w-4 text-health" /></span>
      <div className="min-w-0 max-w-[90%] space-y-2">
        <div dir={rtl ? "rtl" : "ltr"} className={`whitespace-pre-line rounded-2xl rounded-tl-sm px-4 py-2.5 ${turn.error ? "border border-alert/30 bg-alert-soft text-alert" : d?.understanding === "emergency" ? "border-2 border-alert bg-alert-soft" : "bg-paper"}`}>
          {turn.text}
        </div>
        {d && (
          <>
            {d.medicines.length > 0 && (
              <ul className="grid gap-2 sm:grid-cols-2">
                {d.medicines.slice(0, 4).map((m) => (
                  <li key={m.id} className="rounded-xl border border-ink/10 bg-white p-3 text-sm">
                    <div className="flex items-start justify-between gap-2">
                      <p><span className="label-wide font-semibold">{m.brand}</span> <span className="text-clinic">{m.dosage}</span></p>
                      <Stamp status={m.data_status} />
                    </div>
                    <p className="text-xs text-muted">{m.ingredients.map((i) => i.name).join(" + ") || "composition non renseignée"}</p>
                    <p className="mt-1 text-xs">À partir de {mad(m.min_ppv)}</p>
                    <div className="mt-2 flex gap-3 text-xs">
                      <Link href={`/medicines/${m.id}`} className="font-semibold text-clinic underline underline-offset-2">Fiche</Link>
                      <button onClick={() => onAsk(`Quels sont les génériques de ${m.brand} ${m.dosage ?? ""}`.trim())} className="text-clinic underline underline-offset-2">Génériques</button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {d.sources.length > 0 && (
              <p className="text-xs text-muted">Sources : {d.sources.map((s, i) => (
                <span key={s.code}>{i > 0 && " · "}{s.url ? <a href={s.url} target="_blank" rel="noreferrer" className="underline">{s.name}</a> : s.name}
                  {s.data_status === "simulated" && " (simulé)"}</span>))}</p>
            )}
            {d.warnings.map((w) => <p key={w} className="text-xs text-[#6B3E00]">⚠ {w}</p>)}
            <details className="text-xs text-muted">
              <summary className="cursor-pointer">Analyse du message</summary>
              <p className="mt-1">Langue : {LANG[d.language.code] ?? d.language.code} · Intention : {d.intent.resolved} ({Math.round(d.intent.confidence * 100)} %) · Compréhension : {UNDERSTANDING[d.understanding] ?? d.understanding}</p>
              <p>Entités : {[...d.entities.medicines.map((m) => `médicament « ${m.text} » → ${m.brand.toUpperCase()} (${m.method})`),
                ...d.entities.ingredients.map((i) => `substance ${i.name}`), d.entities.dose ? `dosage ${d.entities.dose.text}` : "",
                d.entities.city ? `ville ${d.entities.city}` : ""].filter(Boolean).join(" ; ") || "aucune"}</p>
            </details>
          </>
        )}
      </div>
    </li>
  );
}
