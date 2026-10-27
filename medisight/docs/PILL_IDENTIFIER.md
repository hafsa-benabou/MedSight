# Pill Identifier V1 — reconnaissance des boîtes de médicaments

Périmètre : **boîtes et emballages** de médicaments marocains présents dans le catalogue. La reconnaissance de
comprimés isolés est une extension future. Le résultat est une **aide à l'identification**, jamais une confirmation :
il doit toujours être vérifié par un pharmacien.

## Pipeline
```
Photo (multipart) ─► images.py      type réel (signature), taille ≤ MAX_UPLOAD_MB, décodage, pixels ≤ MAX_IMAGE_PIXELS,
                                    orientation EXIF, réduction à MAX_IMAGE_SIDE, métadonnées supprimées
                 ─► preprocess.py   qualité : netteté (variance du laplacien), luminosité, contraste, résolution,
                                    zones de texte (gradient morphologique) ; variantes : gris, CLAHE, médian+Otsu,
                                    seuillage adaptatif, inversion (fond sombre) ; rotations par quart de tour
                 ─► barcodes.py     zxing-cpp (EAN-13, UPC, ITF-14, DataMatrix GS1) + cv2.barcode en secours,
                                    validation app.core.ean (jamais de correction d'un code invalide)
                 ─► ocr.py          Tesseract fra+ara+eng, psm 11 (texte épars), mots + boîtes + confiances
                 ─► extraction.py   nom (segments, du plus grand texte au plus petit), dosages, concentrations,
                                    substances (vocabulaire de la base, y compris termes BDPM), forme, conditionnement,
                                    laboratoire, chiffres imprimés sous le code-barres
                 ─► matching.py     candidats (code-barres exact, nom flou RapidFuzz, composition), indices par
                                    présentation, indice heuristique 0-100, décision expliquée
                 ─► identify.py     orchestration, statut, trace sans image (identification_results)
```
**Choix de la variante OCR.** Aucune transformation n'est supposée meilleure : les variantes sont lues
successivement et la lecture qui maximise « caractères alphanumériques lus avec confiance ≥ 60 » est retenue ; on
s'arrête dès qu'une lecture est jugée bonne (≥ 25 caractères pondérés, confiance moyenne ≥ 70). Si rien n'est
lisible, les rotations 90°, 270° et 180° sont essayées. Au plus `OCR_MAX_PASSES` passages (6 par défaut).

## API : `POST /api/pills/identify`
Requête `multipart/form-data`, champ `file`. Erreurs du fichier (format JSON habituel `{error: {code, message}}`) :
`415 unsupported_media_type`, `413 file_too_large` / `image_too_large`, `422 corrupted_image` / `empty_file`.
Limitation de débit : `RATE_LIMIT_PILLS` requêtes par minute et par adresse (mécanisme existant).

| Statut (`status`) | Signification |
|---|---|
| `identified` | Indices concordants sans contradiction. `identified_level` = `presentation` (une boîte précise) ou `medicine` (spécialité et dosage sûrs, conditionnement non lu : toutes les présentations possibles sont listées) |
| `ambiguous` | Plusieurs candidats plausibles (jusqu'à 3), ou nom reconnu sans dosage |
| `contradictory` | Le code-barres désigne une présentation que le texte contredit (autre nom, autre dosage, autre substance) |
| `not_found` | Rien ne correspond ; si le nom est reconnu mais pas le dosage, `available_dosages` liste les dosages existants (aucun n'est proposé à la place) |
| `unreadable` | Photo inexploitable (floue, sombre, trop petite, sans texte) et aucun code-barres |
| `ocr_unavailable` | Tesseract absent et aucun code-barres lu |

Champs principaux : `reliability` (`high` / `medium` / `low` / `none`), `reasons`, `warnings`, `barcodes`
(format, code, statut, `in_catalog`, lot et péremption d'un DataMatrix), `extracted`, `candidates` (score,
`evidence` par critère, `explanation`, `source`, statut des données), `presentation_ids`, `ocr` (moteur, langues,
variante et rotation retenues, passages, lignes lues avec confiance et coordonnées), `quality`, `timings_ms`,
`disclaimer`.

### Indice de correspondance (explicable, non calibré)
| Indice | Concordant | Contradictoire |
|---|---|---|
| Code-barres (code lu = EAN-13 de la présentation) | +45 | −35 si le code lu désigne une **autre** présentation du catalogue |
| Nom (similarité RapidFuzz ≥ 80 avec le nom ou une variante sourcée) | +10 à +30 | — |
| Dosage (`strengths_equivalent` : 0,5 g = 500 mg, concentration ≠ dose) | +15 | −40 et candidat écarté |
| Substance active | +10 | −30 |
| Forme canonique | +5 | −10 |
| Conditionnement (`pack_quantity`) | +5 | −10 |

Le total, borné à 0-100, sert à **classer et expliquer**. Ce n'est ni une probabilité ni une précision mesurée.

### Règles de décision
- `identified` exige l'une de ces combinaisons, sans aucune contradiction :
  - code-barres + au moins un indice textuel (nom, dosage ou substance) : `high` ;
  - code-barres seul, quand aucun texte n'a pu être lu : `medium`, avec avertissement ;
  - nom ≥ 90 + dosage concordant : `high` avec un indice de plus (forme, conditionnement ou substance), sinon `medium`.
- Un nom approximatif seul, ou une composition seule, ne donne jamais mieux que `ambiguous`.
- Deux spécialités à moins de 10 points l'une de l'autre donnent `ambiguous`.
- Seules les fiches du marché `MA` sont candidates. Les données `simulated` sont exclues, sauf avec
  `PILL_INCLUDE_SIMULATED=true` (démonstration ; elles restent alors signalées comme simulées).

## Confidentialité
- Image traitée en mémoire, jamais envoyée à un service externe (Tesseract et zxing-cpp tournent en local).
- `STORE_UPLOADED_IMAGES=false` par défaut : rien n'est écrit. Si l'option est activée, une copie ré-encodée **sans
  EXIF** (donc sans position GPS) est écrite dans `data/raw/uploads/` (non versionné).
- La trace `identification_results` conserve l'empreinte SHA-256, les entités extraites, les candidats et la qualité,
  mais **ni l'image ni le texte OCR brut** (une boîte peut porter une étiquette nominative) ; elle expire après
  `IDENTIFICATION_RETENTION_HOURS` (`cli purge-expired`).

## Installation sous Windows
1. Installer Tesseract 5 : programme d'installation de l'UB Mannheim (https://github.com/UB-Mannheim/tesseract/wiki).
   Pendant l'installation, cocher **Additional language data** : *French*, *Arabic* (l'anglais est inclus).
   Ou, en PowerShell : `winget install --id UB-Mannheim.TesseractOCR` (ajouter ensuite `fra.traineddata` et
   `ara.traineddata` de https://github.com/tesseract-ocr/tessdata_fast dans `C:\Program Files\Tesseract-OCR\tessdata`
   si les langues n'ont pas été cochées).
2. Vérifier : `& "C:\Program Files\Tesseract-OCR\tesseract.exe" --list-langs` doit lister `ara`, `eng`, `fra`.
3. Dans `.env` : `TESSERACT_LANGS=fra+ara+eng` et, si `tesseract` n'est pas dans le PATH,
   `TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe`.
4. Dépendances Python : `python -m pip install -r requirements-dev.txt` (ajoute `zxing-cpp`, sans dépendance système).
5. `GET /api/health` → `modules.pill_identifier.ocr.available` doit valoir `true`.

## Corpus de référence (photos réelles)
### Structure
Photos et manifeste dans `data/corpus/` (non versionnés par défaut : vérifier les droits avant toute publication).
Manifeste : `data/templates/pill_corpus_TEMPLATE.csv`. Import : `python -m app.ingestion.cli import-corpus
..\data\corpus\manifest.csv`. Chaque photo devient une ligne `medicine_images`, et sa transcription une ligne
`image_annotations` :

| Donnée | Champ |
|---|---|
| Identifiant de l'image | `medicine_images.id` (+ `sha256` unique : pas de doublon de fichier) |
| Présentation | `presentation_id` : rattachement par EAN-13, sinon par nom + dosage + forme + présentation. Une photo n'est **jamais** rattachée à une présentation absente ou simulée |
| Chemin, source, licence | `file_path`, `source_id` (`pill_corpus`), `license` (obligatoire), `attribution`, `origin` |
| Langue, face | `packaging_languages`, `view` |
| Transcription humaine | `image_annotations` (`ocr_text`, `annotator = human`, `is_verified`) |
| Qualité | `metadata_json.quality` (mesurée à l'import : netteté, luminosité, contraste, zones de texte), `width_px`, `height_px`, `captured_at` |

### Guide : premier corpus de 5 présentations et 30 à 50 photos
1. **Choisir 5 présentations** présentes dans le catalogue, si possible avec un EAN-13 valide, et variées : par
   exemple deux dosages d'une même marque (AMLOR 5 mg et 10 mg), un générique du même groupe (AMEP 5 mg), une crème
   (FUCIDINE 2 %) et un comprimé effervescent (A.V.T.). Vérifier `GET /api/medicines/search?q=<EAN>`.
2. **Se procurer les boîtes** de façon légitime (pharmacie familiale, avec accord). Aucune ordonnance, aucune
   étiquette nominative dans le champ ; masquer ou ne pas photographier ces éléments.
3. **Photographier 6 à 10 vues par présentation** au téléphone :
   - face avant à plat, en lumière du jour ;
   - face avant de biais (≈ 30°) ;
   - dos ou côté portant le code-barres ;
   - côté portant le DataMatrix s'il y en a un ;
   - face avant en lumière artificielle, avec un reflet ;
   - photo volontairement imparfaite (légère inclinaison ou flou de bougé) ;
   - boîte tenue à la main, sur fond encombré.
4. **Nommer les fichiers** `<marque>_<dosage>_<présentation>_<face>_<n°>.jpg` (ex. `amlor_5mg_b28_front_01.jpg`) et
   les placer dans `data/corpus/images/`.
5. **Remplir le manifeste** : une ligne par photo. Indiquer la face, les langues visibles (`fr|ar`), l'origine
   (`team_photo`), la licence (ex. « CC BY 4.0 — équipe MEDISIGHT »), l'auteur, la date, et la **transcription
   humaine** du texte visible (lignes séparées par ` | `), recopiée telle qu'imprimée, sans correction.
6. **Faire relire** chaque ligne par un second membre de l'équipe (présentation, transcription).
7. **Importer** (`import-corpus`), puis **évaluer** (`evaluate-identifier`) : le rapport donne le taux
   d'identifications correctes, le taux d'identifications **erronées** (à maintenir à 0), le top-1 par présentation,
   le top-3 par spécialité, le taux de lecture des codes-barres, la similarité OCR / transcription et la latence
   médiane. Ces mesures servent à recalibrer les seuils de `preprocess.py` et `matching.py`.

Les jeux d'images étrangers (C3PI, ePillID, MEDISEG : voir `DATA_SOURCES.md`) représentent des médicaments
américains ou britanniques. Ils ne sont **jamais** rattachés à des présentations marocaines.

## Limites connues (V1)
- Seuils de qualité et de décision **heuristiques**, non calibrés sur des photos réelles (corpus à constituer).
- Catalogue réel limité (33 spécialités officielles issues des échantillons) : une boîte absente du catalogue donne
  `not_found` même si elle est parfaitement lue.
- OCR de l'arabe : vérifié sur du texte rendu par ordinateur, pas sur des emballages réels ; l'ordre des mots
  arabes dans une ligne peut être inversé (sans effet sur la recherche de termes).
- Pas de redressement de perspective ni de détourage de la boîte (prévu après mesure sur le corpus).
- Aucun modèle d'apprentissage profond (volontairement, tant que le pipeline OCR n'est pas mesuré sur photos réelles).
