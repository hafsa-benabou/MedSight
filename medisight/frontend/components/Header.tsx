"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import Logo from "./Logo";

const NAV: [string, string][] = [
  ["/", "Accueil"], ["/chat", "AI Chatbot"], ["/identify", "Pill Identifier"],
  ["/medicines", "Explorer les médicaments"], ["/about", "À propos"],
];

export default function Header() {
  const path = usePathname();
  return (
    <header className="border-b border-ink/10 bg-white">
      <div className="mx-auto flex max-w-page flex-col gap-2 px-5 py-3 md:h-16 md:flex-row md:items-center md:gap-10 md:py-0">
        <Link href="/" className="flex items-center gap-2.5" aria-label="MEDISIGHT, accueil">
          <Logo />
          <span className="display text-[1.15rem]">MEDISIGHT</span>
        </Link>
        <nav aria-label="Navigation principale" className="-mx-1 flex gap-1 overflow-x-auto text-sm">
          {NAV.map(([href, label]) => {
            const active = href === "/" ? path === "/" : path.startsWith(href);
            return (
              <Link key={href} href={href} aria-current={active ? "page" : undefined}
                className={`whitespace-nowrap rounded-md px-3 py-2 ${active ? "bg-mint font-semibold text-ink" : "text-muted hover:text-ink"}`}>
                {label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
