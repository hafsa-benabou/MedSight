import ModulePending from "@/components/ModulePending";

export default function IdentifyPage() {
  return <ModulePending title="Pill Identifier" lot="lot 3"
    intro="L'identification par photo est en cours de développement. Elle proposera des correspondances possibles, jamais une confirmation."
    items={["Lire le code-barres EAN-13 de la boîte et le rapprocher du Répertoire AMMPS.",
      "Lire le nom et le dosage imprimés (OCR) et contrôler la netteté de la photo.",
      "Classer les trois correspondances les plus probables, avec un score non calibré et sa justification.",
      "Afficher « Identification non fiable » quand les indices sont insuffisants, et ne pas conserver la photo."]} />;
}
