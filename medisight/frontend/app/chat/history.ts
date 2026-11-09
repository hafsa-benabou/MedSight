import type { ChatResponse, MedicineCard } from "@/lib/api";

export type Turn = { id: number; role: "user" | "assistant"; text: string; data?: ChatResponse; error?: { retry?: string } };
/** Conversation affichée : `serverId` est l'identifiant de POST /api/chat, propre à chaque conversation. */
export type Conversation = { id: string; serverId: string | null; title: string; titleEdited: boolean; createdAt: number;
  updatedAt: number; context: MedicineCard | null; pendingContext: number | null; suggestions: string[]; turns: Turn[] };

// Historique local, désactivé par défaut : rien n'est écrit tant que l'utilisateur ne l'a pas activé
const KEY = "medisight.chat.history.v1";
const ENABLED = "medisight.chat.history.enabled";
export const RETENTION_DAYS = 30;
const MAX_CONVERSATIONS = 50;
const DAY = 86_400_000;

export function createConversation(context: MedicineCard | null = null, suggestions: string[] = []): Conversation {
  const now = Date.now();
  return { id: `${now.toString(36)}-${Math.random().toString(36).slice(2, 10)}`, serverId: null, title: "Nouvelle conversation",
    titleEdited: false, createdAt: now, updatedAt: now, context, pendingContext: context?.id ?? null, suggestions, turns: [] };
}

export function readEnabled(): boolean {
  try { return localStorage.getItem(ENABLED) === "1"; } catch { return false; }
}

/** Désactiver efface immédiatement les conversations enregistrées sur l'appareil. */
export function writeEnabled(on: boolean) {
  try {
    if (on) localStorage.setItem(ENABLED, "1");
    else { localStorage.removeItem(ENABLED); localStorage.removeItem(KEY); }
  } catch { /* stockage indisponible (navigation privée, blocage) : l'historique reste en mémoire */ }
}

function prune(list: Conversation[]): Conversation[] {
  const limit = Date.now() - RETENTION_DAYS * DAY;
  return list.filter((c) => c.turns.length > 0 && c.updatedAt >= limit)
    .sort((a, b) => b.updatedAt - a.updatedAt).slice(0, MAX_CONVERSATIONS);
}

const isConversation = (c: unknown): c is Conversation => {
  const x = c as Conversation;
  return !!x && typeof x.id === "string" && typeof x.title === "string" && typeof x.updatedAt === "number" && Array.isArray(x.turns);
};

export function loadConversations(): Conversation[] {
  try {
    const d = JSON.parse(localStorage.getItem(KEY) ?? "null");
    if (d?.version !== 1 || !Array.isArray(d.conversations)) return [];
    return prune(d.conversations.filter(isConversation));
  } catch { return []; }
}

export function saveConversations(list: Conversation[]): boolean {
  try {
    localStorage.setItem(KEY, JSON.stringify({ version: 1, conversations: prune(list) }));
    return true;
  } catch { return false; }
}

// Session en mémoire : conserve les conversations lors de la navigation entre pages, perdue au rechargement
let session: { conversations: Conversation[]; activeId: string } | null = null;
export const readSession = () => session;
export function writeSession(conversations: Conversation[], activeId: string) { session = { conversations, activeId }; }

/** Une question restée sans réponse (page quittée pendant l'analyse) reçoit un message proposant de réessayer. */
export function settle(c: Conversation): Conversation {
  const last = c.turns[c.turns.length - 1];
  if (last?.role !== "user") return c;
  const id = Math.max(...c.turns.map((t) => t.id)) + 1;
  return { ...c, turns: [...c.turns, { id, role: "assistant", text: "La réponse a été interrompue lorsque vous avez quitté la page.",
    error: { retry: last.text } }] };
}

// Titre court déduit de l'analyse renvoyée par l'API (intention, médicament, ville) : aucun service externe
const LABELS: Record<string, [string, string]> = {
  price: ["Prix", "ثمن"], generics: ["Génériques", "بدائل"], active_ingredient: ["Substance active", "المادة الفعالة"],
  dosages: ["Dosages", "العيارات"], presentations: ["Présentations", "العلب"], availability: ["Disponibilité", "توفر"],
};

export function shorten(question: string): string {
  const s = question.replace(/\s+/g, " ").trim().replace(/[\s?؟!.]+$/, "");
  return s.length > 42 ? `${s.slice(0, 40).trimEnd()}…` : s || "Nouvelle conversation";
}

export function titleFrom(question: string, d?: ChatResponse): string {
  if (!d) return shorten(question);
  const ar = d.language.reply_language === "ar";
  const intent = d.intent.resolved;
  if (intent === "pharmacy_search" || intent === "on_duty") {
    const base = intent === "on_duty" ? (ar ? "صيدليات الحراسة" : "Pharmacies de garde") : (ar ? "صيدليات" : "Pharmacies");
    return d.entities.city ? `${base} ${ar ? "في" : "à"} ${d.entities.city}` : base;
  }
  const entity = d.entities.medicines[0];
  const dose = d.entities.dose;
  const med = entity
    ? `${entity.brand.toUpperCase()}${dose ? ` ${dose.value} ${dose.unit ?? ""}`.trimEnd() : ""}`
    : d.context_medicine ? `${d.context_medicine.brand} ${d.context_medicine.dosage ?? ""}`.trim() : null;
  if (!med) return shorten(question);
  const label = LABELS[intent]?.[ar ? 1 : 0];
  return label ? `${label} ${med}` : med;
}

export function groupLabel(ts: number, now = new Date()): string {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  if (ts >= today) return "Aujourd'hui";
  if (ts >= today - DAY) return "Hier";
  if (ts >= today - 6 * DAY) return "7 derniers jours";
  return "Plus ancien";
}

export function stamp(ts: number): string {
  const d = new Date(ts);
  return groupLabel(ts) === "Aujourd'hui"
    ? d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString("fr-FR", { day: "numeric", month: "short" });
}
