# Sources de données — vérification du 25/10/2026

Chaque source a été consultée directement. Le statut indique ce que MEDISIGHT en fait réellement.

## 1. AMMPS — Base de données des médicaments
- **URL :** https://www.ammps.gov.ma/recherche-medicaments
- **Mise à jour affichée :** 01/10/2026. **Volume :** 9 936 médicaments (828 pages de 12 fiches).
- **Champs visibles par fiche :** spécialité, dosage, substance(s) active(s) (séparées par « // »), EPI (laboratoire), forme, présentation, statut de commercialisation (Commercialisé, Non commercialisé, AMM sans prix, Commercialisé AO…), PPV, PH, lien « Télécharger RCP ».
- **Formats de prix rencontrés :** `4.303.00 DH`, `1.200.00 DH`, `10,70 DH`, `SANS PPV DH` (gérés par `parse_price`).
- **Accès :** consultation web ; aucun export ni API publique constaté.
- **Conditions :** le site indique « © 2026 AMMPS. Tous droits réservés ».
- **Usage dans MEDISIGHT :** référence prioritaire pour les prix. Import d'un export CSV/XLSX obtenu auprès de l'AMMPS ou d'une saisie manuelle (`import-ammps`). **Aucun scraper n'est fourni** sans autorisation. Échantillon réel : `data/samples/ammps_medicaments_page1.csv` (page 1, 12 présentations).

## 2. AMMPS — Répertoire Marocain des Médicaments Génériques
- **URL :** https://www.ammps.gov.ma/repertoire-medicaments-generiques
- **Édition :** « Projet – Janvier 2026 », version pilote appelée à évoluer ; 312 substances ; rubrique excipients à effet notoire en cours de finalisation.
- **Structure :** groupe générique (DCI + dosage + forme), voie d'administration, puis membres : type (P = princeps, G = générique, I = valeur présente sans légende), spécialité + présentation, EPI, **EAN-13**.
- **Anomalies d'origine observées (conservées dans l'échantillon) :** EAN absents (« - »), lignes parasites « Groupe gén | - », code à 14 chiffres (CLARISCAN), somme de contrôle EAN invalide (LOWRAC 5 mg boîte de 15).
- **Usage :** équivalences **réglementaires** (distinctes des simples correspondances de composition) et identification des boîtes par code-barres. Échantillon : `data/samples/ammps_generiques_projet_2026-01_extrait.csv`.

## 3. AMMPS — Base de données des pharmacies
- **URL :** https://www.ammps.gov.ma/bases-de-donnees/pharmacies — 8 951 pharmacies.
- **Champs :** nom et ville **uniquement** (ni adresse, ni téléphone, ni coordonnées).
- **Usage :** registre de référence ; les pharmacies OpenStreetMap sont marquées `in_ammps_registry` après rapprochement nom + ville. Échantillon : `data/samples/ammps_pharmacies_page1.csv` (20 entrées).

## 4. CNOPS — Référentiel des médicaments (data.gov.ma)
- **URL :** https://data.gov.ma/data/dataset/referentiel-des-medicaments
- **Licence :** Open Data Commons ODbL (réutilisation libre avec attribution, partage à l'identique des bases dérivées).
- **Ressource :** un seul fichier XLSX `ref-des-medicaments-cnops-2014.xlsx` (≈ 530 Ko), ressource mise à jour le **18/12/2017**, données de **2014**.
- **Contenu annoncé :** type princeps/générique, prix public de vente, prix hôpital, base de remboursement.
- **Usage :** base de remboursement (`reimbursements`). Les prix CNOPS ne remplacent **jamais** un prix AMMPS plus récent ; ils sont conservés comme valeur historique (`ppv_reference_mad`, `valid_as_of`). L'importeur détecte automatiquement la ligne d'en-têtes ; `--dry-run` affiche le mappage des colonnes avant import.

## 5. MedBase (optionnel)
- **Documentation :** https://medbase.ma/api/documentation — base `https://api.medbase.ma/api/v1`, clé `X-API-Key` (ou Bearer), scopes par endpoint.
- **Endpoints :** `/drugs/search`, `/drugs/list`, `/drugs/{uuid}`, `/drugs/{uuid}/similar` (composition, dosage équivalent et forme identiques), `/drugs/{uuid}/rcp`, `/substances/search`, `/laboratories/search`, `/forms`.
- **Accès :** sur demande. **Usage prévu :** source optionnelle de rubriques RCP structurées (statut `reference`), jamais requise par le MVP.

## 6. OpenStreetMap (pharmacies géolocalisées)
- `amenity=pharmacy`, licence ODbL, attribution « © les contributeurs d'OpenStreetMap ».
- `fetch-osm` interroge l'API Overpass (à lancer sur une machine connectée), `import-osm` normalise nom, adresse, téléphone, horaires, coordonnées et rattache la ville (balise `addr:city` ou ville/bourg OSM le plus proche à moins de 25 km).

## 7. Pharmacies de garde
- Les listes de garde proviennent de sites tiers dont les conditions de réutilisation doivent être vérifiées au cas par cas.
- Import manuel sourcé via `data/templates/pharmacies_garde_TEMPLATE.csv` (période, type jour/nuit/24h, URL source).

## 8. Interactions médicamenteuses
- **RxNav (NLM) :** l'API d'interactions a été arrêtée vers le 2 janvier 2024 → non utilisée.
- **DDInter 2.0 :** 302 516 interactions, téléchargements sous **CC BY-NC-SA 4.0** (compatible projet universitaire non commercial). Import `import-interactions --source ddinter` (format `Drug_A, Drug_B, Level`).
- **Thésaurus ANSM :** saisie manuelle sourcée via `interactions_TEMPLATE.csv` (référence obligatoire).
- **Règle :** une substance inconnue est rejetée, jamais créée. L'absence de résultat n'est jamais présentée comme une absence d'interaction.

## 9. Datasets d'images (Pill Identifier, expérimentation)
| Dataset | Contenu | Licence / conditions | Usage |
|---|---|---|---|
| NLM C3PI (RxIMAGE) | 4 000 images de référence (6,8 Go) et 133 000 images grand public | ODbL ; projet arrêté en 2018, images réservées à la R&D | Expérimentation de la similarité visuelle |
| ePillID | 13 000 images, 9 804 classes d'apparence | Code MIT ; données issues des bases NIH (conditions NIH) | Benchmark de récupération top-k |
| MEDISEG | 2 sous-ensembles (3 et 32 classes), masques COCO | CC BY 4.0 | Segmentation de comprimés |

Ces images représentent des médicaments **américains ou britanniques** : elles ne sont jamais associées automatiquement à une spécialité marocaine. La reconnaissance « Maroc » repose sur la boîte (EAN-13 du répertoire, OCR du nom et du dosage).

## 10. Numéros d'urgence (messages de sécurité)
SAMU 141 et Protection civile 15. Le numéro économique du Centre Anti-Poison (0801 000 180) provient d'une source de 2013-2014 : **à revérifier avant toute mise en production** (paramètre `POISON_CENTER`).
