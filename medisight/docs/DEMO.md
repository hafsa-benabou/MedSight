# Scénario de démonstration (≈ 8 minutes)

Préparation : base chargée (`python -m app.ingestion.cli seed`), API sur le port 8000, site sur le port 3000.
Vérifier `http://localhost:8000/api/health` avant de commencer. Préparer une photo nette d'une boîte AMLOR 5 mg
(face avec code-barres) **prise par l'équipe** ; ne pas utiliser d'image dont les droits ne sont pas vérifiés.

| # | Écran | Action | Ce qu'il faut montrer |
|---|---|---|---|
| 1 | Accueil | Présenter les deux cartes « AI Pharmaceutical Assistant » et « AI Pill Identifier » | une seule base PostgreSQL commune, données sourcées |
| 2 | Catalogue | Rechercher `amlor 5 mg`, ouvrir la fiche | prix PPV daté, source AMMPS, génériques du Répertoire (AMEP 5 mg) |
| 3 | Catalogue | Rechercher `doliprane 750 mg` | « dosage non trouvé » : 500 mg et 1000 mg proposés, jamais substitués |
| 4 | Chatbot | `Quels sont les génériques d'AMLOR 5 mg ?` | réponse sourcée, « Analyse du message » : langue fr, intention generics, entités |
| 5 | Chatbot | `Ch7al taman dyal Doliprane 500mg ?` | darija latine comprise ; prix marqué **FICTIF** (fiche simulée) |
| 6 | Chatbot | `Quelles sont les contre-indications d'AMLOR 5 mg ?` | « non disponible dans nos sources » : aucune invention |
| 7 | Chatbot | `j'ai mal à la tête, que prendre ?` | refus d'avis médical, orientation pharmacien |
| 8 | Pill Identifier | Importer (ou glisser) la photo AMLOR 5 mg, « Analyser » | code-barres lu, candidat AMLOR 5 MG, indices expliqués, fiabilité |
| 9 | Pill Identifier → Chatbot | « Poser une question » sur le candidat | bandeau « Médicament de la conversation », suggestions propres à AMLOR |
| 10 | Chatbot | `شنو المادة الفعالة ديال هاد الدوا؟` | réponse en arabe (RTL) : AMLODIPINE, grâce au contexte transmis par identifiant |

Messages clés : le système dit quand il ne sait pas ; les données simulées sont visibles comme telles ;
une identification par photo reste une hypothèse à confirmer par un pharmacien.

## Ce qui n'a PAS été validé (à dire honnêtement)
- Reconnaissance sur des **photographies réelles** : aucun corpus de photos réelles n'est encore constitué (`data/corpus/`).
- OCR Tesseract : validé seulement sur des images de synthèse (voir README, section tests), pas sur des photos de boîtes.
- Si Tesseract n'est pas installé sur la machine de démonstration, l'identification repose sur le seul code-barres
  (statut `ocr_unavailable` si aucun code-barres n'est lu) : lancer l'API via Docker (`docker compose --profile api up -d api`)
  pour disposer de l'OCR.
