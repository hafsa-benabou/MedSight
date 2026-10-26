import Explorer from "./Explorer";

export default async function MedicinesPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const { q } = await searchParams;
  return (
    <div className="mx-auto max-w-page px-5 py-12">
      <h1 className="display text-4xl">Explorer les médicaments</h1>
      <p className="prose-copy mt-3 text-muted">Recherchez par nom commercial, substance active ou dosage. Les fautes de frappe sont tolérées ; le dosage demandé n&apos;est jamais remplacé par un autre.</p>
      <Explorer initialQuery={q ?? ""} />
    </div>
  );
}
