# Chatbot pharmaceutique multilingue (Challenge 1)

Assistant conversationnel qui répond en s'appuyant **uniquement** sur la base PostgreSQL de MEDISIGHT.
Architecture hybride : NLP à base de règles et de lexiques + recherche SQL + génération contrôlée par gabarits.
Aucun modèle de langage externe n'est appelé : le chatbot fonctionne sans clé API, hors ligne.

## Pipeline

```
Message utilisateur
  → normalisation       app/nlp/text.py      minuscules, accents, chiffres arabes, « 500mg » → « 500 mg », arabizi conservé (« ch7al »)
  → langue              app/nlp/language.py  fr | ar | darija (alphabet arabe) | darija_latin (arabizi) | en
  → intention           app/nlp/intents.py   lexiques multilingues, tolérance aux fautes ; urgence / posologie / avis médical prioritaires
  → entités             app/nlp/entities.py  médicament (vocabulaire lu en base), substance, dosage, ville
  → résolution          app/services/chat.py marque + dosage → fiches ; dosage absent = signalé, jamais substitué ; contexte de conversation
  → recherche SQL       catalog / pharmacies / clinical_sections / drug_interactions / generic_groups
  → réponse             gabarits FR / AR ; sources, statut des données, avertissements
```

### Reconnaissance des médicaments
- Correspondance exacte, puis approximative (`rapidfuzz`, seuil 82–88 selon la longueur) : « dolipran » → DOLIPRANE.
- Écriture arabe : squelette consonantique (`skeleton_arabic` / `skeleton_latin`) : « دوليبران » → DOLIPRANE.
- Variantes de noms de la table `medicine_aliases` (écriture arabe, graphie d'emballage) si elles ont été importées.
- Substances actives (noms, synonymes, termes BDPM, nom arabe) reconnues avant les marques.
- Un nombre nu après le nom (« doliprane 500 ») est comparé à la valeur imprimée du dosage, jamais converti.

### Intentions reconnues
| Intention | Exemples | Données utilisées |
|---|---|---|
| `price` | « Ch7al taman dyal Doliprane 500mg ? », « شحال ثمن أملور » | `medicine_presentations.ppv_mad`, date et source |
| `active_ingredient` | « شنو المادة الفعالة ديال هاد الدوا؟ » | `medicine_ingredients` |
| `dosages` | « Quels dosages existent pour AMLOR ? » | toutes les fiches de la marque |
| `presentations` | « Quelles boîtes pour AMLOR 5 mg ? » | présentations, EAN-13 |
| `generics` | « Quels sont les génériques d'AMLOR 5 mg ? » | Répertoire AMMPS (réglementaire) puis même composition (non réglementaire) |
| `indications`, `precautions`, `posology` | « contre-indications de l'amlor » | `clinical_sections` (RCP/notice importés), `drug_interactions` ; sinon « non disponible » |
| `pharmacy_search`, `on_duty` | « Je cherche une pharmacie à Rabat », « pharmacie de garde casa » | `pharmacies`, `pharmacy_duty_shifts` |
| `availability` | « wach kayn doliprane f casa » | statut de commercialisation AMMPS ; stock **jamais** présenté comme vérifié s'il ne l'est pas |
| `medicine_info` | « amlor » | fiche résumée |
| `emergency`, `medical_advice` | « j'ai avalé tout le flacon », « que prendre pour… » | aucune : orientation SAMU 141 / Protection civile 15 / pharmacien |
| `greeting`, `help`, `unknown` | « salam » | — |

### Contexte de conversation
- `context_medicine_id` (envoyé par le Pill Identifier ou une fiche) est **vérifié en base** ; un identifiant inconnu est ignoré avec un avertissement.
- Une question sans médicament (« et son prix ? », « هاد الدوا ») réutilise le médicament de la conversation.
- Après une réponse portant sur une seule marque, celle-ci devient le contexte.

## Règles de sécurité appliquées
1. Aucun prix, stock, posologie, contre-indication, interaction ou garde inventé : absent = « non disponible dans nos sources ».
2. Données simulées signalées dans le texte (« prix FICTIF ») et dans `warnings` / `contains_simulated_data`.
3. Dosage demandé introuvable → `dosage_not_found` avec les dosages disponibles ; aucun prix d'un autre dosage.
4. Pas de diagnostic ni de traitement personnalisé ; la posologie documentée (RCP) s'accompagne d'un renvoi au médecin/pharmacien.
5. Confidentialité : le texte saisi n'est **pas** enregistré (seule l'analyse : langue, intention, entités, 72 h) ;
   `DELETE /api/chat/{id}` efface la conversation.

## LLM
Non intégré dans cette version. Les variables `LLM_PROVIDER` / `LLM_MODEL` restent à `none` ; toute intégration future devra
rester désactivée par défaut, exiger le consentement de l'utilisateur et ne reformuler que des faits issus de la base.

## Limites connues
- Lexiques écrits à la main : couverture partielle de la darija et de l'arabizi ; pas de modèle appris sur un corpus annoté
  (la table `nlp_utterances` est prête pour en constituer un).
- Réponses en darija latine rédigées en français ; réponses arabes en arabe standard simplifié.
- Base de démonstration réduite (≈ 42 fiches) : beaucoup de médicaments réels seront « introuvables ».
- Aucune section clinique (RCP) n'est importée dans la base de démonstration : indications/précautions répondent « non disponible ».
