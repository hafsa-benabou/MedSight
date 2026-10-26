import MedicineDetailView from "./MedicineDetailView";

export default async function MedicinePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <MedicineDetailView id={id} />;
}
