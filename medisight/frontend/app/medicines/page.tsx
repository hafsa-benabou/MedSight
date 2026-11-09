import PageShell from "@/components/PageShell";
import Explorer from "./Explorer";

export default async function MedicinesPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const { q } = await searchParams;
  return (
    <PageShell badge="Catalogue pharmaceutique" title="Explorez les médicaments"
      text="Recherchez un médicament par son nom commercial, sa substance active ou son dosage.">
      <Explorer initialQuery={q ?? ""} />
    </PageShell>
  );
}
