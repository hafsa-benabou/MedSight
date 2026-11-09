import PageShell from "@/components/PageShell";
import PharmacyFinder from "./PharmacyFinder";

export default async function PharmaciesPage({ searchParams }: { searchParams: Promise<{ medicine?: string; city?: string }> }) {
  const sp = await searchParams;
  return (
    <PageShell badge="Répertoire des pharmacies" title="Trouvez une pharmacie"
      text="Consultez les pharmacies référencées dans les données disponibles pour votre ville.">
      <PharmacyFinder medicineId={sp.medicine ?? null} initialCity={sp.city ?? "Casablanca"} />
    </PageShell>
  );
}
