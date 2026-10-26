import PharmacyFinder from "./PharmacyFinder";

export default async function PharmaciesPage({ searchParams }: { searchParams: Promise<{ medicine?: string; city?: string }> }) {
  const sp = await searchParams;
  return (
    <div className="mx-auto max-w-page px-5 py-12">
      <h1 className="display text-4xl">Pharmacies</h1>
      <p className="prose-copy mt-3 text-muted">Pharmacies référencées dans les données importées, avec leur source. Aucune adresse, aucun stock et aucune garde ne sont inventés.</p>
      <PharmacyFinder medicineId={sp.medicine ?? null} initialCity={sp.city ?? "Casablanca"} />
    </div>
  );
}
