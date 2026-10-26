import Link from "next/link";

export default function Footer() {
  return (
    <footer className="mt-24 bg-ink text-white/80">
      <div className="mx-auto grid max-w-page gap-10 px-5 py-12 md:grid-cols-3">
        <div>
          <p className="display text-lg text-white">MEDISIGHT</p>
          <p className="mt-2 text-sm">Your Intelligent Pharmaceutical Companion. Projet ChallengeCamp Data Science, INPT Rabat.</p>
        </div>
        <div className="text-sm">
          <p className="font-semibold text-white">Avertissement</p>
          <p className="mt-2">MEDISIGHT fournit une information, pas un avis médical. Vérifiez toujours auprès d&apos;un pharmacien ou d&apos;un médecin. Urgence : SAMU 141, Protection civile 15.</p>
        </div>
        <div className="text-sm">
          <p className="font-semibold text-white">Données</p>
          <p className="mt-2">AMMPS (consultation publique), CNOPS via data.gov.ma (ODbL), © contributeurs OpenStreetMap (ODbL).</p>
          <p className="mt-2 flex gap-4">
            <Link href="/about#sources" className="underline underline-offset-4">Sources et licences</Link>
            <Link href="/pharmacies" className="underline underline-offset-4">Pharmacies</Link>
          </p>
        </div>
      </div>
    </footer>
  );
}
