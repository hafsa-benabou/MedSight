"use client";
import { HardDrive, MessageSquareText, Pencil, Plus, Trash2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { type Conversation, groupLabel, RETENTION_DAYS, stamp } from "./history";

type Props = {
  conversations: Conversation[]; activeId: string; pendingId: string | null; enabled: boolean; storageError: boolean;
  onSelect: (id: string) => void; onNew: () => void; onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void; onClearAll: () => void; onToggle: (on: boolean) => void; onClose?: () => void;
};
type Confirm = { kind: "delete"; conv: Conversation } | { kind: "clear" } | null;

export default function HistorySidebar(p: Props) {
  const [editing, setEditing] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<Confirm>(null);
  const groups: [string, Conversation[]][] = [];
  for (const c of p.conversations) {
    const g = groupLabel(c.updatedAt);
    const last = groups[groups.length - 1];
    if (last && last[0] === g) last[1].push(c); else groups.push([g, [c]]);
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 p-3">
        <button onClick={p.onNew}
          className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-[#11806B] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[#0c6a58]">
          <Plus aria-hidden className="h-4 w-4" /> Nouvelle conversation
        </button>
        {p.onClose && (
          <button onClick={p.onClose} aria-label="Fermer l'historique" data-autofocus
            className="grid h-10 w-10 place-items-center rounded-lg text-muted transition hover:bg-paper hover:text-ink lg:hidden"><X className="h-5 w-5" /></button>
        )}
      </div>

      <h2 className="px-4 pb-1 pt-2 text-xs font-semibold uppercase tracking-[0.1em] text-muted">Historique des conversations</h2>
      <nav aria-label="Historique des conversations" className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {p.conversations.length === 0 && (
          <p className="px-2 py-4 text-sm text-muted">Vos conversations apparaîtront ici après votre première question.</p>
        )}
        {groups.map(([label, items]) => (
          <section key={label} className="mt-3">
            <h3 className="px-2 text-[11px] font-semibold text-muted/80">{label}</h3>
            <ul className="mt-1 space-y-0.5">
              {items.map((c) => (
                <li key={c.id}>
                  {editing === c.id
                    ? <RenameField title={c.title} onDone={(t) => { if (t) p.onRename(c.id, t); setEditing(null); }} />
                    : <Item c={c} active={c.id === p.activeId} pending={c.id === p.pendingId} onSelect={() => p.onSelect(c.id)}
                        onEdit={() => setEditing(c.id)} onDelete={() => setConfirm({ kind: "delete", conv: c })} />}
                </li>
              ))}
            </ul>
          </section>
        ))}
      </nav>

      <div className="space-y-2 border-t border-ink/10 p-3 text-xs">
        <div className="rounded-xl bg-paper p-3">
          <div className="flex items-center justify-between gap-3">
            <p id="history-switch" className="flex items-center gap-2 font-semibold text-ink"><HardDrive aria-hidden className="h-4 w-4 text-clinic" /> Enregistrer sur cet appareil</p>
            <button role="switch" aria-checked={p.enabled} aria-labelledby="history-switch" onClick={() => p.onToggle(!p.enabled)}
              className={`relative h-6 w-11 shrink-0 rounded-full transition ${p.enabled ? "bg-[#11806B]" : "bg-ink/25"}`}>
              <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-[left] ${p.enabled ? "left-[1.375rem]" : "left-0.5"}`} />
            </button>
          </div>
          <p className="mt-2 leading-relaxed text-muted">
            {p.enabled
              ? `Activé : vos conversations sont stockées dans ce navigateur, sur cet appareil uniquement, ${RETENTION_DAYS} jours au plus. Elles ne sont ni synchronisées ni envoyées à un service externe.`
              : "Désactivé : l'historique est perdu au rechargement de la page. Activez-le pour le conserver dans ce navigateur, sur cet appareil uniquement."}
          </p>
          {p.storageError && <p role="alert" className="mt-2 text-alert">Espace de stockage du navigateur indisponible : l&apos;historique n&apos;a pas pu être enregistré.</p>}
        </div>
        {p.conversations.length > 0 && (
          <button onClick={() => setConfirm({ kind: "clear" })}
            className="flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-muted transition hover:bg-alert-soft hover:text-alert">
            <Trash2 aria-hidden className="h-3.5 w-3.5" /> Effacer tout l&apos;historique
          </button>
        )}
      </div>

      {confirm && (
        <ConfirmDialog
          title={confirm.kind === "clear" ? "Effacer tout l'historique ?" : "Supprimer cette conversation ?"}
          body={confirm.kind === "clear"
            ? "Toutes les conversations seront supprimées de cet appareil, et leur analyse sera effacée du serveur MedSight. Cette action est définitive."
            : `« ${confirm.conv.title} » sera supprimée de cet appareil, et son analyse effacée du serveur MedSight. Cette action est définitive.`}
          action={confirm.kind === "clear" ? "Tout effacer" : "Supprimer"}
          onCancel={() => setConfirm(null)}
          onConfirm={() => { if (confirm.kind === "clear") p.onClearAll(); else p.onDelete(confirm.conv.id); setConfirm(null); }} />
      )}
    </div>
  );
}

function Item({ c, active, pending, onSelect, onEdit, onDelete }: {
  c: Conversation; active: boolean; pending: boolean; onSelect: () => void; onEdit: () => void; onDelete: () => void;
}) {
  return (
    <div className={`group relative flex items-center rounded-lg transition ${active ? "bg-mint" : "hover:bg-paper"}`}>
      {active && <span aria-hidden className="absolute inset-y-2 left-0 w-[3px] rounded-full bg-[#11806B]" />}
      <button onClick={onSelect} aria-current={active ? "page" : undefined} className="flex min-w-0 flex-1 items-start gap-2.5 px-3 py-2 text-left">
        <MessageSquareText aria-hidden className={`mt-0.5 h-4 w-4 shrink-0 ${active ? "text-[#11806B]" : "text-muted/70"}`} />
        <span className="min-w-0 flex-1">
          <span dir="auto" className={`block truncate text-sm ${active ? "font-semibold text-ink" : "text-ink/90"}`}>{c.title}</span>
          <span className="block text-[11px] text-muted">{pending ? "Analyse en cours…" : stamp(c.updatedAt)}{c.context && ` · ${c.context.brand}`}</span>
        </span>
      </button>
      <span className={`flex shrink-0 pr-1 ${active ? "" : "lg:opacity-0 lg:group-focus-within:opacity-100 lg:group-hover:opacity-100"}`}>
        <button onClick={onEdit} aria-label={`Renommer « ${c.title} »`} className="grid h-8 w-8 place-items-center rounded-md text-muted transition hover:bg-white hover:text-ink">
          <Pencil className="h-3.5 w-3.5" /></button>
        <button onClick={onDelete} aria-label={`Supprimer « ${c.title} »`} className="grid h-8 w-8 place-items-center rounded-md text-muted transition hover:bg-white hover:text-alert">
          <Trash2 className="h-3.5 w-3.5" /></button>
      </span>
    </div>
  );
}

function RenameField({ title, onDone }: { title: string; onDone: (t: string | null) => void }) {
  const [value, setValue] = useState(title);
  const ref = useRef<HTMLInputElement>(null);
  const done = useRef(false);
  const finish = (t: string | null) => { if (!done.current) { done.current = true; onDone(t); } };
  useEffect(() => { ref.current?.select(); }, []);
  return (
    <form onSubmit={(e) => { e.preventDefault(); finish(value.trim() || null); }} className="px-1 py-1">
      <label htmlFor="rename-conversation" className="sr-only">Nouveau titre de la conversation</label>
      <input id="rename-conversation" ref={ref} value={value} maxLength={60} dir="auto" onChange={(e) => setValue(e.target.value)}
        onBlur={() => finish(value.trim() || null)} onKeyDown={(e) => { if (e.key === "Escape") { e.preventDefault(); finish(null); } }}
        className="w-full rounded-lg border border-clinic bg-white px-3 py-2 text-sm focus:outline-none focus:ring-4 focus:ring-clinic/10" />
    </form>
  );
}

function ConfirmDialog({ title, body, action, onCancel, onConfirm }: {
  title: string; body: string; action: string; onCancel: () => void; onConfirm: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { ref.current?.showModal(); }, []);
  return (
    <dialog ref={ref} onCancel={(e) => { e.preventDefault(); onCancel(); }} aria-labelledby="confirm-title"
      className="w-[min(26rem,calc(100vw-2rem))] rounded-2xl border border-ink/10 p-6 text-ink shadow-xl backdrop:bg-ink/40">
      <h2 id="confirm-title" className="display text-lg">{title}</h2>
      <p className="mt-3 text-sm leading-relaxed text-muted">{body}</p>
      <div className="mt-6 flex justify-end gap-2">
        <button onClick={onCancel} autoFocus className="rounded-lg border border-ink/15 px-4 py-2 text-sm font-semibold transition hover:border-ink">Annuler</button>
        <button onClick={onConfirm} className="rounded-lg bg-alert px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#8a1f17]">{action}</button>
      </div>
    </dialog>
  );
}
