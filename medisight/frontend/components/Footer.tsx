import Link from "next/link";
import { ShieldAlert } from "lucide-react";
import Logo from "./Logo";

const LINKS: [string, string][] = [["/about", "À propos"], ["/about#sources", "Sources et licences"], ["/medicines", "Catalogue"]];

export default function Footer() {
  return (
    <footer className="mt-24 bg-ink text-white/75">
      <div className="mx-auto grid max-w-page gap-10 px-5 pb-8 pt-14 md:grid-cols-[1.6fr_1fr]">
        <div>
          <Link href="/" className="inline-flex items-center gap-2.5" aria-label="MEDISIGHT, accueil">
            <span className="grid h-9 w-9 place-items-center rounded-lg bg-white"><Logo size={24} /></span>
            <span className="display text-lg text-white">MEDISIGHT</span>
          </Link>
          <p className="mt-4 max-w-md text-sm leading-relaxed">
            Your Health, Our Intelligence. Information pharmaceutique sourcée pour le Maroc. Projet ChallengeCamp Data Science, INPT Rabat.
          </p>
        </div>
        <nav aria-label="Liens du pied de page" className="text-sm">
          <ul className="space-y-2.5">
            {LINKS.map(([href, label]) => (
              <li key={href}><Link href={href} className="underline-offset-4 hover:text-white hover:underline">{label}</Link></li>
            ))}
          </ul>
        </nav>
      </div>
      <div className="border-t border-white/10">
        <div className="mx-auto max-w-page space-y-2 px-5 py-6 text-xs leading-relaxed">
          <p className="flex gap-2 text-white/85">
            <ShieldAlert size={16} aria-hidden="true" className="shrink-0" />
            <span>Information, pas un avis médical : vérifiez toujours auprès d&apos;un pharmacien ou d&apos;un médecin. Urgence : SAMU 141 · Protection civile 15.</span>
          </p>
          <p className="text-white/60">Données : AMMPS (consultation publique), CNOPS via data.gov.ma (ODbL), © contributeurs OpenStreetMap (ODbL).</p>
        </div>
      </div>
    </footer>
  );
}
