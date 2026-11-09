"use client";
import type { LucideIcon } from "lucide-react";
import { ArrowDown, ArrowRight, Coins, FlaskConical, History, Layers, Loader2, MapPin, PanelLeft, Pill, Plus, RotateCcw, SendHorizontal, ShieldCheck, TriangleAlert, X } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import Logo from "@/components/Logo";
import { Stamp } from "@/components/Stamp";
import { api, ApiError, postJson, type ChatResponse, type MedicineCard } from "@/lib/api";
import { day, mad } from "@/lib/format";
import HistorySidebar from "./HistorySidebar";
import { type Conversation, createConversation, loadConversations, readEnabled, readSession, saveConversations, settle, titleFrom, type Turn,
  writeEnabled, writeSession } from "./history";

const STARTERS: [LucideIcon, string, string][] = [
  [Coins, "Prix des médicaments", "Quel est le prix d'AMLOR 5 mg ?"],
  [Layers, "Génériques", "Quels sont les génériques d'AMLOR 5 mg ?"],
  [FlaskConical, "Substance active", "Quelle est la substance active d'AMLOR ?"],
  [MapPin, "Pharmacies", "Je cherche une pharmacie à Rabat."],
];
const MORE = ["Ch7al taman dyal Abilify 10 mg ?", "شنو المادة الفعالة ديال AMLOR؟", "Quels dosages existent pour AMLOR ?"];

const UNAVAILABLE = "Le service MedSight est temporairement indisponible. Veuillez réessayer.";
// Cas particuliers signalés par le moteur : le texte de la réponse vient toujours de l'API
const NOTICE: Record<string, [string, "alert" | "care" | "info"]> = {
  emergency: ["Urgence", "alert"],
  refused_medical_advice: ["Question nécessitant un avis médical", "care"],
  not_found: ["Médicament introuvable", "info"],
  dosage_not_found: ["Dosage non référencé", "info"],
  information_unavailable: ["Information absente des sources", "info"],
  ambiguous: ["Question ambiguë", "info"],
  clarification_needed: ["Précision demandée", "info"],
  not_understood: ["Question non comprise", "info"],
};
const TONE = { alert: "border-alert/40 bg-alert-soft text-alert", care: "border-sim/40 bg-sim-soft text-[#6B3E00]", info: "border-clinic/25 bg-[#E6F1F7] text-ink" };
const UNDERSTANDING: Record<string, string> = {
  understood: "compris", partial: "compris partiellement", ambiguous: "ambigu", not_found: "médicament introuvable",
  clarification_needed: "précision demandée", dosage_not_found: "dosage non référencé", information_unavailable: "information absente des sources",
  refused_medical_advice: "avis médical refusé", emergency: "urgence", not_understood: "non compris",
};
const LANG: Record<string, string> = { fr: "français", ar: "arabe", darija: "darija (arabe)", darija_latin: "darija (latin)", en: "anglais" };
const PANEL_H = "lg:h-[calc(100dvh-16.5rem)] lg:min-h-[32rem]";
const isArabic = (s: string) => /[؀-ۿ]/.test(s);
const key = (s: string) => s.toLowerCase().replace(/[\s?.!؟]+/g, " ").trim();

/** Message affiché à la place d'une erreur technique : jamais de trace, jamais de réponse de substitution. */
function friendly(e: unknown): { text: string; retry: boolean } {
  const status = e instanceof ApiError ? e.status : 0;
  if (status === 429) return { text: "Trop de questions en peu de temps : patientez une minute avant de réessayer.", retry: true };
  if (status === 422) return { text: "Ce message n'a pas pu être traité. Reformulez votre question (1 000 caractères au maximum).", retry: false };
  return { text: UNAVAILABLE, retry: true };
}

const eraseOnServer = (c: Conversation) => {
  if (c.serverId) void fetch(`/api/chat/${c.serverId}`, { method: "DELETE" }).catch(() => undefined);
};

export default function Chat() {
  const params = useSearchParams();
  const router = useRouter();
  const [initial] = useState(() => createConversation());
  const [convs, setConvs] = useState<Conversation[]>([initial]);
  const [activeId, setActiveId] = useState(initial.id);
  const [pending, setPending] = useState<string | null>(null);
  const [resumed, setResumed] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [contextError, setContextError] = useState<string | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [storageError, setStorageError] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [jump, setJump] = useState<"new" | "down" | null>(null);
  const sectionRef = useRef<HTMLElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const lastTop = useRef(0);
  const seen = useRef({ conv: "", len: 0 });
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const pendingRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const nextId = useRef(1);

  const active = convs.find((c) => c.id === activeId) ?? convs[0];
  const busy = pending !== null;
  const patch = (id: string, f: (c: Conversation) => Conversation) => setConvs((cs) => cs.map((c) => (c.id === id ? f(c) : c)));

  // Retour sur la page : conversations de la session en mémoire ; sinon historique local, uniquement si l'utilisateur l'a activé
  useEffect(() => {
    const on = readEnabled();
    setEnabled(on);
    const mem = readSession();
    const stored = (mem ? mem.conversations : on ? loadConversations() : []).map(settle);
    nextId.current = Math.max(1, ...stored.flatMap((c) => c.turns.map((t) => t.id + 1)));
    if (mem && stored.length) {
      setConvs(stored);
      setActiveId(stored.some((c) => c.id === mem.activeId) ? mem.activeId : stored[0].id);
    } else if (stored.length) {
      setConvs((cs) => [...cs.filter((c) => !stored.some((s) => s.id === c.id)), ...stored]);
    }
    setLoaded(true);
    return () => abortRef.current?.abort();
  }, []);

  useEffect(() => {
    if (loaded) writeSession(convs, activeId);
  }, [convs, activeId, loaded]);

  useEffect(() => {
    if (loaded && enabled) setStorageError(!saveConversations(convs));
  }, [convs, enabled, loaded]);

  // Contexte transmis par le Pill Identifier ou une fiche : nouvelle conversation, identifiant PostgreSQL vérifié par l'API
  useEffect(() => {
    const raw = params.get("medicine");
    const id = raw && /^\d+$/.test(raw) ? Number(raw) : null;
    if (!id) return;
    const ctrl = new AbortController();
    api<{ medicine: MedicineCard; suggestions: string[] }>(`/api/chat/suggestions?medicine_id=${id}`, ctrl.signal)
      .then((d) => {
        const c = createConversation(d.medicine, d.suggestions);
        setConvs((cs) => [c, ...cs.filter((x) => x.turns.length > 0)]);
        setActiveId(c.id);
        setResumed(null);
        setContextError(null);
      })
      .catch((e: Error) => {
        if (e.name === "AbortError") return;
        setContextError(e instanceof ApiError && e.status === 404 ? "Le médicament transmis est introuvable dans le catalogue." : UNAVAILABLE);
      });
    return () => ctrl.abort();
  }, [params]);

  // Défilement : suit la conversation tant que l'utilisateur est en bas, sans jamais le ramener de force s'il relit
  useEffect(() => {
    const el = listRef.current;
    if (!el) return;
    const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
    const turns = active.turns;
    const last = turns[turns.length - 1];
    if (seen.current.conv !== active.id) {
      seen.current = { conv: active.id, len: turns.length };
      stick.current = true;
      setJump(null);
      el.scrollTop = turns.length ? el.scrollHeight : 0;
      lastTop.current = el.scrollTop;
      return;
    }
    const grew = turns.length > seen.current.len;
    seen.current.len = turns.length;
    if (!grew) {
      if (pending === active.id && stick.current) el.scrollTo({ top: el.scrollHeight, behavior });
      return;
    }
    if (last.role === "user") {
      stick.current = true;
      setJump(null);
      el.scrollTo({ top: el.scrollHeight, behavior });
    } else if (!stick.current) {
      setJump("new");
    } else {
      showTurn(last.id, behavior);
    }
  }, [active.turns, active.id, pending]);

  // Une longue réponse (fiches médicaments) s'affiche à partir de son début plutôt que de sa fin
  function showTurn(id: number, behavior: ScrollBehavior) {
    const el = listRef.current;
    const node = el?.querySelector<HTMLElement>(`[data-turn="${id}"]`);
    if (!el) return;
    if (node && node.offsetHeight > el.clientHeight - 48) el.scrollTo({ top: node.offsetTop - 16, behavior });
    else el.scrollTo({ top: el.scrollHeight, behavior });
  }

  // Seul un défilement vers le haut (geste de l'utilisateur) suspend le suivi : un défilement animé vers le bas ne le coupe pas
  function onListScroll() {
    const el = listRef.current;
    if (!el) return;
    const up = el.scrollTop < lastTop.current - 2;
    lastTop.current = el.scrollTop;
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 120) {
      stick.current = true;
      setJump(null);
    } else if (up) {
      stick.current = false;
      if (active.turns.length) setJump((j) => j ?? "down");
    }
  }

  function jumpDown() {
    const last = active.turns[active.turns.length - 1];
    if (jump === "new" && last) showTurn(last.id, "smooth");
    else listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
    setJump(null);
  }

  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [input]);

  useEffect(() => {
    if (!drawer) return;
    document.querySelector<HTMLElement>("#chat-history [data-autofocus]")?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") closeDrawer(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawer]);

  function closeDrawer() {
    setDrawer(false);
    toggleRef.current?.focus();
  }

  async function send(text: string, retryOf?: number) {
    const message = text.trim();
    if (!message || pendingRef.current) return;
    const conv = active;
    pendingRef.current = conv.id;
    setPending(conv.id);
    if (retryOf === undefined) {
      const id = nextId.current++;
      // Sur petit écran, le panneau est ramené dans la vue pour que la saisie et la réponse restent visibles
      const box = sectionRef.current?.getBoundingClientRect();
      if (box && (box.bottom > window.innerHeight + 1 || box.top < 0)) sectionRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
      setInput("");
      patch(conv.id, (c) => ({ ...c, updatedAt: Date.now(), title: c.turns.length || c.titleEdited ? c.title : titleFrom(message),
        turns: [...c.turns, { id, role: "user", text: message }] }));
    } else {
      patch(conv.id, (c) => ({ ...c, turns: c.turns.filter((x) => x.id !== retryOf) }));
    }
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    const id = nextId.current++;
    try {
      // Chaque conversation envoie son propre identifiant serveur et son propre médicament de contexte
      const data = await postJson<ChatResponse>("/api/chat", {
        message, conversation_id: conv.serverId, context_medicine_id: conv.pendingContext ?? undefined }, ctrl.signal);
      patch(conv.id, (c) => {
        const first = !c.turns.some((t) => t.data);
        const question = c.turns.find((t) => t.role === "user")?.text ?? message;
        return { ...c, serverId: data.conversation_id, pendingContext: null, context: data.context_medicine,
          suggestions: data.suggestions.length ? data.suggestions : c.suggestions, updatedAt: Date.now(),
          title: first && !c.titleEdited ? titleFrom(question, data) : c.title,
          turns: [...c.turns, { id, role: "assistant", text: data.message, data }] };
      });
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      const f = friendly(e);
      patch(conv.id, (c) => ({ ...c, turns: [...c.turns, { id, role: "assistant", text: f.text, error: { retry: f.retry ? message : undefined } }] }));
    } finally {
      if (abortRef.current === ctrl) {
        abortRef.current = null;
        pendingRef.current = null;
        setPending(null);
      }
    }
  }

  function stopPending(ids: string[]) {
    if (pendingRef.current && ids.includes(pendingRef.current)) {
      abortRef.current?.abort();
      abortRef.current = null;
      pendingRef.current = null;
      setPending(null);
    }
  }

  // Nouvelle conversation : affichage seulement, l'historique et la base ne sont pas touchés
  function newChat() {
    const c = active.turns.length === 0 && !active.context ? active : createConversation();
    setConvs((cs) => [c, ...cs.filter((x) => x.id !== c.id && x.turns.length > 0)]);
    setActiveId(c.id);
    setResumed(null);
    setContextError(null);
    setInput("");
    if (params.get("medicine")) router.replace("/chat");
    setDrawer(false);
    inputRef.current?.focus();
  }

  function select(id: string) {
    if (id !== activeId) {
      // Reprise : le médicament de cette conversation est renvoyé, au cas où la session serveur (72 h) aurait expiré
      patch(id, (c) => ({ ...c, pendingContext: c.context?.id ?? null }));
      setConvs((cs) => cs.filter((x) => x.id === id || x.turns.length > 0));
      setActiveId(id);
      setResumed(id);
      setInput("");
    }
    setContextError(null);
    setDrawer(false);
  }

  function remove(id: string) {
    const c = convs.find((x) => x.id === id);
    if (c) eraseOnServer(c);
    stopPending([id]);
    const rest = convs.filter((x) => x.id !== id);
    if (id === activeId || rest.length === 0) {
      const fresh = createConversation();
      setConvs([fresh, ...rest.filter((x) => x.turns.length > 0)]);
      setActiveId(fresh.id);
      setResumed(null);
    } else {
      setConvs(rest);
    }
  }

  function clearAll() {
    convs.forEach(eraseOnServer);
    stopPending(convs.map((c) => c.id));
    const fresh = createConversation();
    setConvs([fresh]);
    setActiveId(fresh.id);
    setResumed(null);
    setInput("");
  }

  function toggleStorage(on: boolean) {
    writeEnabled(on);
    setEnabled(on);
    setStorageError(false);
  }

  function removeContext() {
    // Un nouvel identifiant serveur garantit que le médicament retiré n'est plus utilisé comme contexte
    patch(active.id, (c) => ({ ...c, context: null, pendingContext: null, serverId: null }));
    if (params.get("medicine")) router.replace("/chat");
  }

  const welcome = active.turns.length === 0;
  const context = active.context;
  const starters: [LucideIcon, string, string][] = context && active.suggestions.length
    ? active.suggestions.slice(0, 4).map((s) => [Pill, `${context.brand} ${context.dosage ?? ""}`.trim(), s])
    : STARTERS;
  const asked = new Set(active.turns.filter((t) => t.role === "user").map((t) => key(t.text)));
  const composerChips = welcome ? MORE : active.suggestions.filter((s) => !asked.has(key(s))).slice(0, 4);
  const listed = convs.filter((c) => c.turns.length > 0).sort((a, b) => b.updatedAt - a.updatedAt);

  return (
    <div className="mt-6 grid gap-5 lg:grid-cols-[17.5rem_minmax(0,1fr)]">
      {drawer && <div aria-hidden className="fixed inset-0 z-40 bg-ink/40 lg:hidden" onClick={closeDrawer} />}
      <aside id="chat-history" aria-label="Historique des conversations"
        className={`fixed inset-y-0 left-0 z-50 w-[min(20rem,86vw)] bg-white shadow-xl transition-[transform,visibility] duration-200 motion-reduce:transition-none
          lg:visible lg:static lg:z-auto lg:w-auto lg:translate-x-0 lg:overflow-hidden lg:rounded-2xl lg:border lg:border-ink/10 lg:shadow-[0_1px_2px_rgba(18,59,93,0.04),0_12px_32px_-18px_rgba(18,59,93,0.18)] ${PANEL_H}
          ${drawer ? "visible translate-x-0" : "invisible -translate-x-full"}`}>
        <HistorySidebar conversations={listed} activeId={active.id} pendingId={pending} enabled={enabled} storageError={storageError}
          onSelect={select} onNew={newChat} onRename={(id, title) => patch(id, (c) => ({ ...c, title, titleEdited: true }))}
          onDelete={remove} onClearAll={clearAll} onToggle={toggleStorage} onClose={closeDrawer} />
      </aside>

      <section ref={sectionRef} aria-label="Conversation"
        className={`flex h-[80dvh] min-h-[30rem] flex-col overflow-hidden rounded-2xl border border-ink/10 bg-white shadow-[0_1px_2px_rgba(18,59,93,0.04),0_12px_32px_-18px_rgba(18,59,93,0.18)] ${PANEL_H}`}>
        <div className="flex items-center gap-2 border-b border-ink/10 px-3 py-2 md:px-5">
          <button ref={toggleRef} onClick={() => setDrawer(true)} aria-controls="chat-history" aria-expanded={drawer}
            className="inline-flex h-9 items-center gap-2 rounded-lg px-2 text-sm font-semibold text-muted transition hover:bg-paper hover:text-ink lg:hidden">
            <PanelLeft aria-hidden className="h-5 w-5" /><span className="sr-only sm:not-sr-only">Historique</span>
          </button>
          <p dir="auto" className="min-w-0 flex-1 truncate py-1.5 text-sm font-semibold text-ink">{welcome ? "Nouvelle conversation" : active.title}</p>
          <button onClick={newChat} aria-label="Nouvelle conversation"
            className="grid h-9 w-9 place-items-center rounded-lg text-muted transition hover:bg-paper hover:text-ink lg:hidden"><Plus className="h-5 w-5" /></button>
        </div>
        {context && (
          <div className="flex items-center gap-3 border-b border-ink/10 bg-mint/60 px-4 py-2.5 text-sm">
            <Pill aria-hidden className="h-4 w-4 shrink-0 text-[#11806B]" />
            <p className="min-w-0 flex-1 truncate"><span className="hidden sm:inline">Médicament de la conversation</span><span className="sm:hidden">Médicament</span> : <Link href={`/medicines/${context.id}`} className="font-semibold underline underline-offset-2"><bdi>{context.brand} {context.dosage}</bdi></Link>
              {context.data_status === "simulated" && <span className="ml-2"><Stamp status="simulated" /></span>}</p>
            <button onClick={removeContext} aria-label="Retirer le médicament de la conversation"
              className="rounded-md p-1 transition hover:bg-white"><X className="h-4 w-4" /></button>
          </div>
        )}
        {contextError && <p role="alert" className="border-b border-alert/20 bg-alert-soft px-4 py-2 text-sm text-alert">{contextError}</p>}

        <div className="relative min-h-0 flex-1">
        <div ref={listRef} onScroll={onListScroll} className={`relative h-full overflow-y-auto px-4 [scrollbar-width:thin] md:px-8 lg:overscroll-y-contain ${welcome ? "py-4" : "py-5"}`}>
          {welcome && (
            <div className="mx-auto flex min-h-full max-w-3xl flex-col items-center justify-center text-center">
              <span aria-hidden className="grid h-12 w-12 place-items-center rounded-2xl bg-mint"><Logo size={30} /></span>
              <h2 className="display mt-4 text-2xl md:text-[1.75rem]">Bonjour, je suis MedSight AI !</h2>
              <p className="mt-2.5 text-muted">Votre assistant d&apos;information pharmaceutique dédié aux médicaments disponibles au Maroc.</p>
              <p className="mt-1 font-semibold">Comment puis-je vous aider aujourd&apos;hui ?</p>
              <ul className="mt-4 grid w-full gap-2.5 sm:grid-cols-2">
                {starters.map(([Icon, label, q]) => (
                  <li key={q}>
                    <button onClick={() => send(q)} disabled={busy}
                      className="group flex h-full w-full items-start gap-3 rounded-xl border border-ink/10 bg-paper/60 px-4 py-3.5 text-left transition hover:border-health/50 hover:bg-white hover:shadow-[0_8px_24px_-14px_rgba(18,59,93,0.25)] disabled:opacity-60">
                      <span aria-hidden className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-white text-[#11806B] transition group-hover:bg-mint"><Icon size={18} /></span>
                      <span className="min-w-0">
                        <span className="block text-xs font-semibold uppercase tracking-[0.08em] text-muted">{label}</span>
                        <span dir="auto" className="mt-1 block text-sm font-medium text-ink">{q}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
              <p className="mt-3 max-w-xl text-xs leading-relaxed text-muted">
                Sur le serveur MedSight, le texte de vos questions n&apos;est pas conservé ; seule son analyse l&apos;est 72 h.{" "}
                <Link href="/about" className="font-semibold text-clinic underline underline-offset-2">En savoir plus</Link>
              </p>
            </div>
          )}
          {resumed === active.id && !welcome && (
            <p className="mx-auto mb-5 flex max-w-2xl items-start gap-2 rounded-xl bg-paper px-4 py-2.5 text-xs leading-relaxed text-muted">
              <History aria-hidden className="mt-px h-4 w-4 shrink-0 text-clinic" />
              Conversation reprise. MedSight ne relit pas les messages précédents : seul le médicament de la conversation, s&apos;il y en a un, sert de contexte aux nouvelles questions.
            </p>
          )}
          <ol className="space-y-6" aria-live="polite">
            {active.turns.map((t) => <Message key={t.id} turn={t} busy={busy} onAsk={send} onRetry={(text) => send(text, t.id)} />)}
            {pending === active.id && (
              <li className="msg-in flex items-center gap-3" role="status">
                <span aria-hidden className="grid h-8 w-8 shrink-0 place-items-center rounded-full border border-ink/10 bg-white"><Logo size={20} /></span>
                <span className="inline-flex items-center gap-3 rounded-2xl rounded-tl-md border border-ink/10 bg-paper px-4 py-3 text-sm text-muted">
                  <span aria-hidden className="flex gap-1"><i className="typing-dot" /><i className="typing-dot" /><i className="typing-dot" /></span>
                  MedSight recherche dans les données pharmaceutiques…
                </span>
              </li>
            )}
          </ol>
        </div>
          {jump && (
            <button onClick={jumpDown}
              className="msg-in absolute bottom-3 left-1/2 inline-flex -translate-x-1/2 items-center gap-1.5 rounded-full border border-ink/10 bg-white px-3.5 py-2 text-xs font-semibold text-ink shadow-[0_8px_24px_-10px_rgba(18,59,93,0.35)] transition hover:bg-mint">
              <ArrowDown aria-hidden className="h-3.5 w-3.5" /> {jump === "new" ? "Nouvelle réponse" : "Revenir en bas"}
            </button>
          )}
        </div>

        <form onSubmit={(e) => { e.preventDefault(); void send(input); }} className="border-t border-ink/10 bg-white px-3 pb-3 md:px-5 md:pb-4">
          {composerChips.length > 0 && (
            <div role="group" aria-label="Questions suggérées" className={`-mx-1 flex gap-2 px-1 pt-3 ${welcome
              ? "flex-wrap items-center justify-center"
              : "overflow-x-auto [mask-image:linear-gradient(to_right,#000_88%,transparent)] [scrollbar-width:none]"}`}>
              {welcome && <span className="text-xs text-muted">Essayez aussi :</span>}
              {composerChips.map((s) => (
                <button key={s} type="button" onClick={() => send(s)} disabled={busy} dir="auto"
                  className="shrink-0 rounded-full border border-ink/15 bg-white px-3 py-1.5 text-xs transition hover:border-health/50 hover:bg-mint disabled:opacity-50">{s}</button>
              ))}
            </div>
          )}
          <div className="mt-3 flex items-end gap-2 rounded-2xl border border-ink/15 bg-paper/60 p-1.5 transition focus-within:border-clinic focus-within:bg-white focus-within:ring-4 focus-within:ring-clinic/10">
            <label htmlFor="chat-input" className="sr-only">Votre question</label>
            <textarea id="chat-input" ref={inputRef} rows={1} value={input} onChange={(e) => setInput(e.target.value)} maxLength={1000}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void send(input); }
              }}
              dir={isArabic(input) ? "rtl" : "auto"} placeholder="Posez votre question sur un médicament..." autoComplete="off"
              aria-describedby="chat-hint"
              className="max-h-40 min-h-11 flex-1 resize-none bg-transparent px-3 py-2.5 leading-relaxed placeholder:text-muted/80 focus:outline-none" />
            <button type="submit" disabled={busy || !input.trim()} aria-label={busy ? "Analyse en cours" : "Envoyer"}
              className="inline-flex h-11 shrink-0 items-center gap-2 rounded-xl bg-[#11806B] px-4 font-semibold text-white transition hover:bg-[#0c6a58] disabled:cursor-not-allowed disabled:bg-ink/25">
              {busy ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <SendHorizontal aria-hidden className="h-4 w-4" />}
              <span className="hidden sm:inline">Envoyer</span>
            </button>
          </div>
          <div className="mt-2 flex flex-col gap-1 px-1 text-[11px] leading-relaxed text-muted md:flex-row md:justify-between md:gap-6">
            <p id="chat-hint" className="hidden shrink-0 md:block">Entrée pour envoyer · Maj+Entrée pour aller à la ligne</p>
            <p className="flex gap-1.5 md:max-w-2xl"><ShieldCheck aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-clinic" />
              Les réponses MedSight sont élaborées à partir des données pharmaceutiques disponibles. Elles ne remplacent pas les conseils d&apos;un professionnel de santé.</p>
          </div>
        </form>
      </section>
    </div>
  );
}

function Message({ turn, busy, onAsk, onRetry }: { turn: Turn; busy: boolean; onAsk: (s: string) => void; onRetry: (s: string) => void }) {
  const rtl = turn.role === "assistant" ? turn.data?.language.reply_language === "ar" : isArabic(turn.text);
  if (turn.role === "user") {
    return (
      <li className="msg-in flex justify-end">
        <p dir={rtl ? "rtl" : "auto"} className={`max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-ink px-4 py-3 text-white ${rtl ? "leading-loose" : "leading-relaxed"}`}>
          <span className="sr-only">Vous : </span>{turn.text}
        </p>
      </li>
    );
  }
  const d = turn.data;
  const notice = d ? NOTICE[d.understanding] : undefined;
  const bubble = turn.error ? "border-alert/30 bg-alert-soft text-alert"
    : d?.understanding === "emergency" ? "border-2 border-alert bg-alert-soft" : "border-ink/10 bg-paper";
  return (
    <li data-turn={turn.id} className="msg-in flex gap-3">
      <span aria-hidden className="mt-0.5 hidden h-8 w-8 shrink-0 place-items-center rounded-full border border-ink/10 bg-white sm:grid"><Logo size={20} /></span>
      <div className="min-w-0 flex-1 space-y-3">
        <p className="flex items-center gap-2 text-xs font-semibold text-ink"><span aria-hidden className="sm:hidden"><Logo size={16} /></span>MedSight AI</p>
        {notice && (
          <p className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold ${TONE[notice[1]]}`}>
            {notice[1] !== "info" && <TriangleAlert aria-hidden className="h-3.5 w-3.5" />}{notice[0]}
          </p>
        )}
        <div dir={rtl ? "rtl" : "ltr"}
          className={`w-fit max-w-full whitespace-pre-wrap break-words rounded-2xl rounded-tl-md border px-4 py-3 ${rtl ? "leading-loose" : "leading-relaxed"} ${bubble}`}>
          {turn.error && <TriangleAlert aria-hidden className="-mt-0.5 me-2 inline h-4 w-4" />}{turn.text}
        </div>
        {turn.error?.retry && (
          <button onClick={() => onRetry(turn.error!.retry!)} disabled={busy}
            className="inline-flex items-center gap-2 rounded-lg border border-ink/15 bg-white px-3 py-2 text-sm font-semibold transition hover:border-ink disabled:opacity-50">
            <RotateCcw aria-hidden className="h-4 w-4" /> Réessayer
          </button>
        )}
        {d && (
          <>
            {d.medicines.length > 0 && (
              <ul className="grid grid-cols-1 gap-3 xl:grid-cols-2">
                {d.medicines.slice(0, 4).map((m) => <MedicineResult key={m.id} m={m} busy={busy} onAsk={onAsk} />)}
              </ul>
            )}
            {d.medicines.length > 4 && (
              <p className="text-xs text-muted">{d.medicines.length - 4} autre(s) résultat(s) :{" "}
                <Link href={`/medicines?q=${encodeURIComponent(d.medicines[0].brand)}`} className="font-semibold text-clinic underline underline-offset-2">voir le catalogue</Link></p>
            )}
            {d.sources.length > 0 && (
              <p className="text-xs text-muted">Sources : {d.sources.map((s, i) => (
                <span key={s.code}>{i > 0 && " · "}{s.url ? <a href={s.url} target="_blank" rel="noreferrer" className="underline underline-offset-2 hover:text-ink">{s.name}</a> : s.name}
                  {s.data_status === "simulated" && !/simulé/i.test(s.name) && " (simulé)"}</span>))}</p>
            )}
            {d.warnings.map((w) => (
              <p key={w} className="flex gap-1.5 text-xs text-[#6B3E00]"><TriangleAlert aria-hidden className="mt-px h-3.5 w-3.5 shrink-0" />{w}</p>
            ))}
            <details className="text-xs text-muted">
              <summary className="cursor-pointer select-none hover:text-ink">Analyse du message</summary>
              <div className="mt-2 space-y-1 rounded-lg border border-ink/10 bg-white p-3">
                <p>Langue : {LANG[d.language.code] ?? d.language.code} · Intention : {d.intent.resolved} ({Math.round(d.intent.confidence * 100)} %) · Compréhension : {UNDERSTANDING[d.understanding] ?? d.understanding}</p>
                <p>Entités : {[...d.entities.medicines.map((m) => `médicament « ${m.text} » → ${m.brand.toUpperCase()} (${m.method})`),
                  ...d.entities.ingredients.map((i) => `substance ${i.name}`), d.entities.dose ? `dosage ${d.entities.dose.text}` : "",
                  d.entities.city ? `ville ${d.entities.city}` : ""].filter(Boolean).join(" ; ") || "aucune"}</p>
                <p className="italic">Indicateurs techniques de l&apos;analyse automatique, et non une garantie médicale.</p>
              </div>
            </details>
          </>
        )}
      </div>
    </li>
  );
}

/** Carte construite uniquement à partir des champs renvoyés par l'API ; une valeur absente reste absente. */
function MedicineResult({ m, busy, onAsk }: { m: MedicineCard; busy: boolean; onAsk: (s: string) => void }) {
  const priced = m.presentations.find((p) => p.ppv != null && p.ppv === m.min_ppv);
  const asOf = day(priced?.price_as_of);
  const substances = m.ingredients.map((i) => i.name).join(" + ");
  const rows: [string, string | null][] = [
    ["Substance active", substances || null],
    ["Forme", m.form],
    ["Laboratoire", m.laboratory],
    ["Prix", m.min_ppv != null ? `${m.presentations.length > 1 ? "À partir de " : ""}${mad(m.min_ppv)} (PPV${asOf ? `, au ${asOf}` : ""})` : null],
  ];
  return (
    <li className="flex flex-col rounded-xl border border-ink/10 bg-white p-4 shadow-[0_6px_18px_-14px_rgba(18,59,93,0.3)]">
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1.5">
        <p dir="ltr" className="min-w-0"><span className="label-wide font-semibold">{m.brand}</span>{m.dosage && <span className="ml-1.5 font-semibold text-clinic">{m.dosage}</span>}</p>
        {(m.source || m.data_status !== "official") && <Stamp status={m.data_status} />}
      </div>
      <dl className="mt-3 space-y-1.5 text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="grid grid-cols-[6.5rem_minmax(0,1fr)] gap-2 sm:grid-cols-[7.5rem_minmax(0,1fr)]">
            <dt className="text-muted">{k}</dt>
            <dd className={`break-words ${v ? "" : "text-muted"}`}>{v ?? (k === "Prix" ? "Prix non disponible" : "Non renseigné")}</dd>
          </div>
        ))}
      </dl>
      {m.source && (
        <p className="mt-2 text-xs text-muted">Source : {m.source.url
          ? <a href={m.source.url} target="_blank" rel="noreferrer" className="underline underline-offset-2 hover:text-ink">{m.source.name}</a>
          : m.source.name}</p>
      )}
      <div className="mt-auto flex flex-wrap items-center gap-x-4 gap-y-2 pt-4">
        <Link href={`/medicines/${m.id}`} className="inline-flex items-center gap-1.5 rounded-lg bg-ink px-3 py-2 text-xs font-semibold text-white transition hover:bg-[#0d2f4b]">
          Consulter la fiche médicament <ArrowRight aria-hidden className="h-3.5 w-3.5" />
        </Link>
        <button onClick={() => onAsk(`Quels sont les génériques de ${m.brand} ${m.dosage ?? ""}`.trim())} disabled={busy}
          className="text-xs font-semibold text-clinic underline underline-offset-2 disabled:opacity-50">Voir les génériques</button>
      </div>
    </li>
  );
}
