import type { Metadata } from "next";
import Identifier from "./Identifier";

export const metadata: Metadata = { title: "Pill Identifier — MEDISIGHT" };

export default function IdentifyPage() {
  return (
    <div className="mx-auto max-w-page px-5 py-12">
      <p className="label-wide text-sm text-clinic">Challenge 2 · Vision par ordinateur + OCR + PostgreSQL</p>
      <h1 className="display mt-2 text-4xl md:text-5xl">Pill Identifier</h1>
      <p className="prose-copy mt-4 text-lg text-muted">
        Photographiez la face d&apos;une boîte portant le nom, le dosage ou le code-barres. MEDISIGHT lit le code-barres et le texte imprimé,
        puis rapproche ces indices du catalogue marocain. Le résultat est une hypothèse, à faire confirmer par un pharmacien.
      </p>
      <Identifier />
    </div>
  );
}
