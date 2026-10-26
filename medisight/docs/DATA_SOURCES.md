# Sources de données — vérification du 25/10/2026, mise à jour le 26/10/2026 (phase 1 « enrichissement »)

Chaque source a été consultée directement. Le statut indique ce que MEDISIGHT en fait réellement.
Chaque source porte un **marché** (`data_sources.market` : `MA`, `FR`, `US`, `INT`) : aucune donnée de marché étranger
(présentation, prix, spécialité) n'entre dans le catalogue marocain ; le contrôle qualité `foreign_market_in_catalog` le vérifie.

## Synthèse (26/10/2026)
| Source | Accès constaté | Licence | Intégré | Statut des données | Rôle |
|---|---|---|---|---|---|
| AMMPS médicaments | Consultation web (9 936 fiches, MAJ 01/10/2026), aucun export, aucune URL de fiche | © tous droits réservés | Échantillon transcrit (12 lignes) + importeur d'export prêt | `official` | Prix, statut, composition |
| AMMPS répertoire génériques | Consultation web, édition projet janvier 2026, pas de téléchargement | Pas de conditions explicites (site © AMMPS) | Extrait transcrit (28 lignes) + importeur prêt | `official` | Équivalences réglementaires, EAN-13 |
| CNOPS (data.gov.ma) | **HTTP 503** le 26/10/2026 (Retry-After 3600) : fichier non téléchargeable | ODbL 1.0 | Importeur prêt, non exécuté sur le fichier réel | `official` (historique 2014) | Base de remboursement |
| BDPM (France) | Téléchargement libre, fichiers mensuels | Licence Ouverte Etalab 2.0 | **Oui** : `CIS_COMPO_bdpm.txt` (32 439 lignes) | `reference`, marché `FR` | Terminologie des substances uniquement |
| DailyMed / RxNorm / OpenFDA | Accessibles sans clé (voir § 10 bis) | Domaine public US / conditions NLM | Non | — | Faible pertinence pour le Maroc |
| MedBase | Clé API requise, non disponible | Conditions MedBase | Non | — | Optionnel |

## 1. AMMPS — Base de données des médicaments
- **URL :** https://www.ammps.gov.ma/recherche-medicaments
- **Mise à jour affichée :** 01/10/2026. **Volume :** 9 936 médicaments (828 pages de 12 fiches).
- **Champs visibles par fiche :** spécialité, dosage, substance(s) active(s) (séparées par « // »), EPI (laboratoire), forme, présentation, statut de commercialisation (Commercialisé, Non commercialisé, AMM sans prix, Commercialisé AO…), PPV, PH, lien « Télécharger RCP ».
- **Formats de prix rencontrés :** `4.303.00 DH`, `1.200.00 DH`, `10,70 DH`, `SANS PPV DH` (gérés par `parse_price`).
- **Accès :** consultation web ; aucun export ni API publique constaté (revérifié le 26/10/2026). Pas d'URL individuelle par fiche (le lien RCP est une action JavaScript) : la provenance est donc la page de recherche + la date de mise à jour de la base.
- **Conditions :** le site indique « © 2026 AMMPS. Tous droits réservés ».
- **Usage dans MEDISIGHT :** référence prioritaire pour les prix. Import d'un export CSV/XLSX obtenu auprès de l'AMMPS ou d'une saisie manuelle (`import-ammps`). **Aucun scraper n'est fourni** sans autorisation. Échantillon réel : `data/samples/ammps_medicaments_page1.csv` (page 1, 12 présentations).
- **Champs couverts par l'importeur :** nom commercial, DCI (substances séparées par `//` ou `+`), dosage, forme, présentation, EPI, statut de commercialisation, PPV, PH, PFHT, EAN-13, ATC, lien RCP, URL de fiche (`URL FICHE`, si l'export en fournit une) ; la date de mise à jour est passée par `--version-date`.
- **Champs absents des données intégrées :** EAN-13 (absent du site, fourni par le répertoire), code ATC, classe thérapeutique, prix hospitalier des produits « AMM sans prix ».
- **Méthode légale et reproductible proposée :** (1) demande écrite d'export à l'AMMPS (modèle de colonnes : `data/templates/ammps_medicaments_TEMPLATE.csv`), en précisant l'usage académique non commercial ; (2) à défaut, transcription manuelle ciblée de pages consultées, avec date de consultation en en-tête du fichier et `method=manual_transcription` ; (3) import par `import-ammps --version-date`, puis `quality --strict`.

## 2. AMMPS — Répertoire Marocain des Médicaments Génériques
- **URL :** https://www.ammps.gov.ma/repertoire-medicaments-generiques
- **Édition :** « Projet – Janvier 2026 », version pilote appelée à évoluer ; 312 substances ; rubrique excipients à effet notoire en cours de finalisation.
- **Structure :** groupe générique (DCI + dosage + forme), voie d'administration, puis membres : type (P = princeps, G = générique, I = valeur présente sans légende), spécialité + présentation, EPI, **EAN-13**.
- **Anomalies d'origine observées (conservées dans l'échantillon) :** EAN absents (« - »), lignes parasites « Groupe gén | - », code à 14 chiffres (CLARISCAN), somme de contrôle EAN invalide (LOWRAC 5 mg boîte de 15).
- **Usage :** équivalences **réglementaires** (distinctes des simples correspondances de composition) et identification des boîtes par code-barres. Échantillon : `data/samples/ammps_generiques_projet_2026-01_extrait.csv`.
- **Vérification des correspondances (depuis le 26/10/2026) :** un membre n'est rattaché à une spécialité que si son **dosage** (comparaison numérique : « 0,02 » = « 2 % », « 0,5 G » = « 500 MG ») et sa **forme canonique** sont ceux du groupe ; sinon il est conservé avec `match_method = inconsistent`, sans rattachement. La **présentation** est rattachée par libellé exact. Le dosage et la forme du groupe servent d'ancres pour découper le libellé (corrige « FUSIDATE PHARMA 5 2% CREME », auparavant enregistré avec le dosage « 5 2% »).
- **Codes-barres :** un code à 14 chiffres est un GTIN-14 ; celui de CLARISCAN (`27037960641780`) a une clé GS1 **valide** mais un indicateur logistique (2) : il est conservé (`ean_status = gtin14`) sans être utilisé comme EAN-13 de la boîte. Un GTIN-14 commençant par 0 (lecture DataMatrix) est ramené à l'EAN-13.

## 3. AMMPS — Base de données des pharmacies
- **URL :** https://www.ammps.gov.ma/bases-de-donnees/pharmacies — 8 951 pharmacies.
- **Champs :** nom et ville **uniquement** (ni adresse, ni téléphone, ni coordonnées).
- **Usage :** registre de référence ; les pharmacies OpenStreetMap sont marquées `in_ammps_registry` après rapprochement nom + ville. Échantillon : `data/samples/ammps_pharmacies_page1.csv` (20 entrées).

## 4. CNOPS — Référentiel des médicaments (data.gov.ma)
- **URL :** https://data.gov.ma/data/dataset/referentiel-des-medicaments
- **Licence :** Open Data Commons ODbL (réutilisation libre avec attribution, partage à l'identique des bases dérivées).
- **Ressource :** un seul fichier XLSX `ref-des-medicaments-cnops-2014.xlsx` (≈ 530 Ko), ressource mise à jour le **18/12/2017**, données de **2014**.
- **Contenu annoncé :** type princeps/générique, prix public de vente, prix hôpital, base de remboursement.
- **Disponibilité au 26/10/2026 :** la page du jeu de données et son API renvoient **HTTP 503** (« Retry-After: 3600 ») ; le fichier n'a pu être ni téléchargé ni vérifié. L'importeur reste celui du MVP (détection automatique de la ligne d'en-têtes ; colonnes `NOM`, `DCI1`, `DOSAGE1`, `UNITE_DOSAGE1`, `FORME`, `PRESENTATION`, `PPV`, `PH`, `PRIX_BR`, `PRINCEPS_GENERIQUE`, `TAUX_REMBOURSEMENT` et variantes) : lancer d'abord `import-cnops … --dry-run` et contrôler le mappage affiché.
- **Usage :** base de remboursement (`reimbursements`). **Changement du 26/10/2026 :** les prix CNOPS (2014) ne sont **plus recopiés** dans les présentations, même quand l'AMMPS n'a pas de prix : ils restent uniquement des valeurs historiques datées (`ppv_reference_mad`, `ph_reference_mad`, `valid_as_of`). Ils ne peuvent donc ni écraser un prix AMMPS ni être affichés comme prix actuel (contrôle `historical_price_as_current`). Seul un EAN-13 valide enrichit la présentation. Un ré-import ne remplace que les lignes de la même version (`valid_as_of`).

## 4 bis. BDPM — Base de données publique des médicaments (France)
- **URL :** https://base-donnees-publique.medicaments.gouv.fr/telechargement — fichiers texte tabulés, Latin-1, actualisés **chaque mois** (au 26/10/2026 : `CIS_bdpm.txt` du 29/09/2026, `CIS_CIP_bdpm.txt` du 26/10/2026).
- **Licence :** Licence Ouverte **Etalab 2.0** (réutilisation libre avec mention de la source et de la date).
- **Intégré :** `CIS_COMPO_bdpm.txt` (téléchargé le 26/10/2026, 32 439 lignes : 26 915 SA, 5 524 FT), via `import-bdpm`. Fichier conservé dans `data/raw/` (non versionné).
- **Ce qui est importé :** pour les substances **déjà présentes** dans la base marocaine, le code substance BDPM de la fraction thérapeutique (`active_ingredients.external_codes`) et les noms de sels (`search_terms`, ex. « BÉSILATE D'AMLODIPINE », « CHLORHYDRATE DE METFORMINE »), utilisés **uniquement pour la recherche** : ils ne servent jamais à résoudre une substance à l'import, car un dosage exprimé en sel n'est pas un dosage en base.
- **Règles strictes, établies sur le fichier réel :** correspondance sur le nom exact de la substance (pas les synonymes) ; le sel doit contenir ce nom ; un terme désignant une autre substance de la base est écarté. Faux positifs ainsi évités : « COCARBOXYLASE » (thiamine), « DOTA » et « OXYDE DE GADOLINIUM » (acide gadotérique), « LACTOBIONATE D'ÉRYTHROMYCINE » (éthylsuccinate), « ACÉTYLSALICYLATE DE DL-LYSINE » (acide acétylsalicylique). Résultat : 12 substances reçoivent un code BDPM, 8 reçoivent des termes de sel.
- **Ce qui n'est jamais importé :** spécialités, présentations, prix, CIP, dosages, textes cliniques français (marché distinct).

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

## 10 bis. Autres sources examinées (26/10/2026, non intégrées)
| Source | Données | Accès / restrictions | Mise à jour | Pertinence Maroc |
|---|---|---|---|---|
| DailyMed (NLM) | Notices SPL des médicaments **américains** | Téléchargement et API publics sans clé | Quotidienne | Faible : spécialités et présentations US ; au mieux documentation en anglais, jamais un prix ni une présentation |
| RxNorm (NLM) | Terminologie (ingrédients, RxCUI, noms anglais) | API RxNav sans clé ; fichiers complets soumis à la licence UMLS ; API d'interactions arrêtée en janvier 2024 | Mensuelle | Moyenne pour la colonne `inn_en` (nom anglais), sinon faible |
| OpenFDA | Étiquetage, NDC, effets indésirables (US) | API publique, clé facultative (quotas réduits sans clé) | Hebdomadaire à trimestrielle | Faible : marché US |
| MedBase | Spécialités marocaines, RCP structurés | Clé API sur demande, **non disponible** | Non documentée | Élevée si l'accès est obtenu ; non intégrée (pas d'API sans clé disponible) |

## 10. Numéros d'urgence (messages de sécurité)
SAMU 141 et Protection civile 15. Le numéro économique du Centre Anti-Poison (0801 000 180) provient d'une source de 2013-2014 : **à revérifier avant toute mise en production** (paramètre `POISON_CENTER`).
