import type { Metadata } from "next";
import PageShell from "@/components/PageShell";
import Identifier from "./Identifier";

export const metadata: Metadata = { title: "Pill Identifier — MEDISIGHT" };

export default function IdentifyPage() {
  return (
    <PageShell badge="Reconnaissance visuelle intelligente" title="Pill Identifier"
      text="Importez une photo de votre boîte de médicament. MedSight analyse son emballage pour rechercher des correspondances dans notre catalogue pharmaceutique.">
      <Identifier />
    </PageShell>
  );
}
