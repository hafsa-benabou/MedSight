import ModulePending from "@/components/ModulePending";

export default function ChatPage() {
  return <ModulePending title="MediSight AI" lot="lot 2b"
    intro="L'assistant conversationnel est en cours de développement. Il répondra en français, en arabe et en darija, à partir des seules données sourcées."
    items={["Comprendre « ch7al taman Doliprane ? », « واش كاين Doliprane 500mg ؟ » ou « Quel est le prix du Doliprane ? » comme la même demande.",
      "Afficher l'interprétation structurée de chaque message : langue, intention, médicament, dosage, ville.",
      "Répondre avec la source et la date de chaque donnée, et dire clairement quand une information manque.",
      "Orienter vers le SAMU (141) ou un professionnel de santé dès qu'une question présente un risque."]} />;
}
