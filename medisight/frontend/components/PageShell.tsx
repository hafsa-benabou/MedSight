import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

/** Carte HealthTech partagée avec l'accueil et le chatbot. */
export const CARD = "rounded-2xl border border-ink/10 bg-white shadow-[0_1px_2px_rgba(18,59,93,0.04),0_12px_32px_-18px_rgba(18,59,93,0.18)]";

/** Pages intérieures : même fond, même badge et même hiérarchie typographique que la page du chatbot. */
export default function PageShell({ badge, title, text, children }: { badge: string; title: string; text: string; children: ReactNode }) {
  return (
    <div className="bg-[linear-gradient(#FFFFFF,#F5F8FA_22rem)]">
      <div className="mx-auto max-w-page px-5 pb-4 pt-8 md:pt-10">
        <header className="fade-up max-w-3xl">
          <p className="inline-flex items-center gap-2 rounded-full border border-health/30 bg-white px-3 py-1 text-[0.68rem] font-semibold uppercase tracking-[0.08em] text-[#11806B] sm:text-xs">
            <span aria-hidden="true">✦</span> {badge}
          </p>
          <h1 className="display mt-4 text-3xl text-ink md:text-[2.6rem]">{title}</h1>
          <p className="prose-copy mt-3 text-muted">{text}</p>
        </header>
        {children}
      </div>
    </div>
  );
}

export function EmptyState({ Icon, title, children }: { Icon: LucideIcon; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center px-6 py-12 text-center">
      <span aria-hidden className="grid h-14 w-14 place-items-center rounded-2xl bg-mint text-[#11806B]"><Icon size={26} /></span>
      <p className="mt-4 font-semibold text-ink">{title}</p>
      {children && <div className="mt-1.5 max-w-md text-sm leading-relaxed text-muted">{children}</div>}
    </div>
  );
}

export function Spinner({ label }: { label: string }) {
  return (
    <p role="status" className="flex items-center justify-center gap-3 py-12 text-sm text-muted">
      <span aria-hidden className="flex gap-1"><i className="typing-dot" /><i className="typing-dot" /><i className="typing-dot" /></span>{label}
    </p>
  );
}
