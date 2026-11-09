# MEDSIGHT — Your Health, Our Intelligence.

**Plateforme intelligente d'information pharmaceutique et de reconnaissance visuelle des médicaments pour le Maroc.**

Projet réalisé dans le cadre du **ChallengeCamp Data Science** de l'Institut National des Postes et Télécommunications
(**INPT, Rabat**) par **Hafsa Benabou** et **Khalid Elharmoud**.

> MedSight fournit une information, pas un avis médical. Toute identification par image reste une hypothèse
> à faire vérifier par un pharmacien. Urgences : SAMU 141, Protection civile 15.

---

## Sommaire
1. [Présentation](#1-présentation)
2. [Fonctionnalités](#2-fonctionnalités)
3. [Architecture et technologies](#3-architecture-et-technologies)
4. [Organisation du dépôt](#4-organisation-du-dépôt)
5. [Installation et démarrage](#5-installation-et-démarrage)
6. [API REST](#6-api-rest)
7. [Tests](#7-tests)
8. [Sources de données, couverture et limites](#8-sources-de-données-couverture-et-limites)
9. [Documentation détaillée](#9-documentation-détaillée)

---

## 1. Présentation

### Problématique
Au Maroc, l'information pharmaceutique est **dispersée** entre plusieurs référentiels (base des médicaments de
l'AMMPS, Répertoire des génériques, référentiel CNOPS…), les questions sont posées en **français, en arabe, en darija
ou en arabizi** (« ch7al taman… »), et l'utilisateur ne dispose parfois que de la **boîte** du médicament.

> Comment concevoir une plateforme unifiée permettant de comprendre des demandes pharmaceutiques multilingues et
> d'identifier des médicaments à partir de leurs emballages, tout en garantissant la traçabilité des informations ?

### Objectifs
- Rechercher un médicament par nom commercial, substance active, dosage ou code-barres, en tolérant les fautes.
- Comprendre des questions en français, arabe et darija, et répondre uniquement à partir de données sourcées.
- Proposer des médicaments candidats à partir de la photo d'une boîte, avec des indices expliqués.
- Relier les deux modules : un médicament identifié par photo devient le contexte de la conversation.
- Ne jamais inventer une donnée (prix, stock, garde, posologie) ni remplacer un dosage demandé par un autre.

### Les deux challenges, un seul dépôt
| Challenge | Module | Code |
|---|---|---|
| **1. Chatbot pharmaceutique multilingue** | NLP à base de règles et de lexiques + recherche SQL + réponses par gabarits | `backend/app/nlp/`, `backend/app/services/chat.py`, `frontend/app/chat/` |
| **2. Reconnaissance visuelle des médicaments** | Traitement d'image OpenCV, codes-barres, OCR Tesseract, rapprochement avec le catalogue | `backend/app/vision/`, `frontend/app/identify/` |

Les deux modules partagent la **même base PostgreSQL** et la même API FastAPI.

---

## 2. Fonctionnalités

| Fonctionnalité | Description |
|---|---|
| **Chatbot multilingue** | Français, arabe (affichage de droite à gauche), darija en alphabet arabe et en arabizi ; réponses en français ou en arabe |
| **Analyse NLP** | Normalisation, détection de langue, 16 intentions (prix, substance active, dosages, génériques, pharmacies, garde…), entités (médicament, substance, dosage, ville) |
| **Tolérance aux fautes** | Correspondance approximative `rapidfuzz` (« dolipran » → DOLIPRANE) et similarité trigramme `pg_trgm` ; le dosage demandé n'est **jamais** substitué |
| **Pill Identifier** | Import, glisser-déposer ou caméra ; contrôle qualité, codes-barres EAN-13 / DataMatrix GS1, OCR Tesseract `fra+ara+eng`, extraction du nom et du dosage |
| **Rapprochement PostgreSQL** | Candidats classés par un indice heuristique 0-100 expliqué, statut (`identified`, `ambiguous`, `not_found`…) et fiabilité |
| **Catalogue** | Recherche, fiches médicament (présentations, EAN-13, prix datés et sourcés), génériques réglementaires distingués de la simple même composition |
| **Pharmacies** | Recherche par ville et par nom ; adresse, téléphone, stock et gardes affichés « non disponible » quand la source ne les fournit pas |
| **Historique des conversations** | Enregistré dans le navigateur (`localStorage`), désactivé par défaut et activable par l'utilisateur |
| **Intégration des deux challenges** | Bouton « Poser une question à MedSight AI » : `/chat?medicine=<id>` transmet l'identifiant PostgreSQL au chatbot, revérifié par l'API |
| **Traçabilité** | Chaque valeur porte sa source, sa date de version et un statut : `official`, `reference`, `unverified` ou `simulated` |

---

## 3. Architecture et technologies

```
                    ┌──────────────── Next.js 15 (frontend/) ────────────────┐
                    │  /chat  (Chat.tsx)        /identify  (Identifier.tsx)  │
                    │      ▲  « Poser une question » : /chat?medicine=<id>   │
                    └──────┼────────────── /api/* (rewrite) ───────┼─────────┘
                           │                                       │
          POST /api/chat   ▼                FastAPI (backend/)     ▼  POST /api/pills/identify
   app/nlp : text → language → intents → entities         app/vision : images → preprocess → barcodes
   app/services/chat.py : résolution, contexte, réponses             → ocr (Tesseract) → extraction → matching
                           │                                       │
                           └──────────► PostgreSQL 16 ◄────────────┘
              medicines, medicine_presentations (PPV, EAN-13), active_ingredients, generic_groups,
              pharmacies, conversations / messages (analyse seule, 72 h), identification_results (empreinte, 24 h)
```

| Couche | Technologies (versions des fichiers de dépendances) | Rôle |
|---|---|---|
| Présentation | **Next.js 15**, React 19, TypeScript, Tailwind CSS 3, lucide-react, police Archivo | Interface, navigation, import de photos, historique local |
| Application | **FastAPI**, Pydantic v2, pydantic-settings, Uvicorn | Endpoints REST, validation, limitation de débit, documentation OpenAPI |
| NLP | Python (`re`, `unicodedata`), **rapidfuzz** | Normalisation, langue, intentions, entités ; aucun LLM (`LLM_PROVIDER=none`) |
| Vision / OCR | **OpenCV** (`opencv-python-headless`), Pillow, NumPy, **zxing-cpp**, **pytesseract** + **Tesseract 5** | Qualité d'image, variantes, codes-barres, OCR, extraction |
| Données | **PostgreSQL 16** (extension `pg_trgm`), SQLAlchemy 2, psycopg 3, **Alembic** | 24 tables, migrations `0001` et `0002`, provenance des données |
| Import | openpyxl, pdfplumber, httpx | Lecture CSV/XLSX, extraction de rubriques RCP, OpenStreetMap |
| Environnement | **Docker Compose**, pytest, GitLab CI (`.gitlab-ci.yml`) | Base conteneurisée, API conteneurisée avec Tesseract, tests |

`requirements-ml.txt` (torch, easyocr…) liste des backends **expérimentaux non utilisés** par la version livrée.

---

## 4. Organisation du dépôt

```
medisight/
├── backend/                 API FastAPI (Python 3.11+)
│   ├── app/
│   │   ├── api/routes/      endpoints REST
│   │   ├── core/            configuration (.env), erreurs, EAN, limitation de débit
│   │   ├── db/              session SQLAlchemy
│   │   ├── ingestion/       importeurs et CLI (seed, quality, stats…)
│   │   ├── nlp/             Challenge 1 : text, language, intents, entities, cities
│   │   ├── services/        catalogue, pharmacies, chat (résolution et réponses)
│   │   ├── vision/          Challenge 2 : images, preprocess, barcodes, ocr, extraction, matching, identify
│   │   └── models.py        modèle de données (24 tables)
│   ├── alembic/             migrations du schéma
│   ├── tests/               tests pytest
│   ├── Dockerfile           API + Tesseract (fra, ara, eng)
│   └── requirements*.txt
├── frontend/                site Next.js (app/, components/, lib/api.ts)
├── database/init/           extensions PostgreSQL (pg_trgm, unaccent) au premier démarrage
├── data/                    échantillons officiels transcrits, démo simulée, référentiels, modèles d'import
├── docs/                    documentation technique (chatbot, API, vision, données, démonstration)
├── docker-compose.yml       service db (+ service api avec le profil « api »)
├── Makefile                 raccourcis (db, migrate, seed, test, stats)
└── .env.example             modèle de configuration
```

---

## 5. Installation et démarrage

### 5.1 Prérequis
| Outil | Version | Usage |
|---|---|---|
| Git | — | cloner le dépôt |
| Docker Desktop (ou Docker Engine + Compose) | récent | PostgreSQL 16 ; API avec OCR en option |
| Python | **3.11** ou plus récent | backend |
| Node.js | **20** ou plus récent | frontend |
| Tesseract OCR 5 + langues `fra`, `ara`, `eng` | optionnel en local | OCR du Pill Identifier (inclus dans l'image Docker de l'API) |

Prévoir environ 2 Go d'espace disque pour l'image Docker de l'API si vous utilisez l'option 5.7 B.

### 5.2 Cloner le projet
```bash
git clone https://github.com/hafsa-benabou/MedSight.git
cd MedSight/medisight
```
Toutes les commandes ci-dessous partent du dossier `medisight/`.

### 5.3 Configurer l'environnement
```bash
cp .env.example .env            # PowerShell : Copy-Item .env.example .env
```
Les valeurs par défaut fonctionnent en local (utilisateur, mot de passe et base `medisight`). Changez
`POSTGRES_PASSWORD` **et** `DATABASE_URL` ensemble avant tout déploiement. Les clés `*_API_KEY` restent vides :
aucune n'est nécessaire.

### 5.4 Démarrer PostgreSQL
```bash
docker compose up -d db
docker compose ps               # le service db doit être « healthy »
```
Sous Windows, arrêtez un éventuel service PostgreSQL local qui occuperait déjà le port 5432.

### 5.5 Installer le backend
```bash
cd backend
python -m venv .venv
# Windows PowerShell : .venv\Scripts\Activate.ps1      Linux / macOS : source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

### 5.6 Créer le schéma et charger les données
```bash
python -m alembic upgrade head                # révisions 0001 + 0002
python -m app.ingestion.cli seed              # référentiel, échantillons officiels, démonstration simulée
python -m app.ingestion.cli quality --strict  # contrôle qualité (code de sortie 1 si un contrôle critique échoue)
python -m app.ingestion.cli stats             # nombre d'enregistrements
```
Optionnel : enrichir la terminologie des substances avec la BDPM française (fichier non redistribué ici,
téléchargeable sous Licence Ouverte Etalab 2.0 sur https://base-donnees-publique.medicaments.gouv.fr/telechargement) :
```bash
python -m app.ingestion.cli import-bdpm ../data/raw/bdpm_AAAA-MM-JJ/CIS_COMPO_bdpm.txt --version-date AAAA-MM-JJ
```

### 5.7 OCR du Pill Identifier : deux options
**A. Tesseract installé localement (Windows)**
1. Installer Tesseract 5 (UB Mannheim, https://github.com/UB-Mannheim/tesseract/wiki) en cochant les langues
   *French* et *Arabic*, ou `winget install --id UB-Mannheim.TesseractOCR`.
2. Vérifier : `& "C:\Program Files\Tesseract-OCR\tesseract.exe" --list-langs` doit lister `ara`, `eng`, `fra`.
3. Si Tesseract n'est pas dans le PATH, renseigner dans `.env` :
   `TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe`.

**B. API dans Docker (Tesseract déjà inclus)** — à la place de l'étape 5.8 :
```bash
docker compose --profile api build api
docker compose --profile api up -d api        # API avec OCR sur http://localhost:8000
```

Sans Tesseract, l'identification fonctionne avec le seul code-barres (statut `ocr_unavailable` si aucun code n'est lu).

### 5.8 Démarrer l'API FastAPI
```bash
# depuis medisight/backend, environnement virtuel activé
python -m uvicorn app.main:app --reload --port 8000
```
Vérifier http://localhost:8000/api/health (base, OCR, lecteurs de codes-barres) et la documentation interactive
http://localhost:8000/docs.

### 5.9 Installer et démarrer le frontend
Dans un second terminal :
```bash
cd medisight/frontend
npm install
npm run dev
```

### 5.10 Accéder à l'interface
Ouvrir **http://localhost:3000**. Le site relaie ses appels `/api/*` vers `http://localhost:8000`
(variable `BACKEND_URL` pour une autre adresse).

| Page | Adresse |
|---|---|
| Accueil | `/` |
| AI Chatbot (Challenge 1) | `/chat` |
| Pill Identifier (Challenge 2) | `/identify` |
| Catalogue | `/medicines` |
| Pharmacies | `/pharmacies` |
| À propos | `/about` |

Scénario de démonstration conseillé : `docs/DEMO.md`.

---

## 6. API REST

Référence complète : `docs/API.md` et http://localhost:8000/docs.

| Méthode | Chemin | Rôle |
|---|---|---|
| GET | `/api/health` | état de la base et des modules (OCR, codes-barres) |
| GET | `/api/sources` | sources chargées, licences, dernier import |
| GET | `/api/medicines/search?q=` | recherche tolérante aux fautes ; EAN-13 accepté ; `dosage_found`, `available_dosages` |
| GET | `/api/medicines/{id}` | fiche : présentations, prix sourcés, sections cliniques |
| GET | `/api/medicines/{id}/generics` | génériques réglementaires et de même composition |
| GET | `/api/pharmacies/search?city=&q=` | pharmacies, disponibilité qualifiée |
| GET | `/api/pharmacies/on-duty?city=` | pharmacies de garde vérifiées |
| POST | `/api/chat` | **Challenge 1** : `{ "message", "conversation_id", "context_medicine_id" }` |
| GET | `/api/chat/suggestions?medicine_id=` | questions suggérées pour un médicament |
| DELETE | `/api/chat/{conversation_id}` | effacer une conversation |
| POST | `/api/pills/identify` | **Challenge 2** : multipart, champ `file` (JPEG, PNG, WEBP ≤ 8 Mo) |

Exemple :
```bash
curl -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" \
     -d '{"message": "Ch7al taman dyal AMLOR 5 mg ?"}'
```

---

## 7. Tests

```bash
cd medisight/backend
python -m pytest -q                 # crée et utilise une base dédiée « medisight_test » (la base principale n'est pas modifiée)
cd ../frontend
npx tsc --noEmit                    # vérification des types
npx next build                      # compilation de production
```
Les tests nécessitent PostgreSQL démarré (étape 5.4). Les tests de `tests/test_vision_tesseract.py` sont ignorés si
Tesseract est absent ; pour tout exécuter avec l'OCR réel :
```bash
docker compose --profile api run --rm api python -m pytest -q
```
La CI GitLab (`.gitlab-ci.yml`) exécute la suite avec Tesseract installé.

| Fichier | Couverture |
|---|---|
| `test_ingestion.py`, `test_data_quality.py`, `test_public_data.py` | imports, normalisation des prix et dosages, EAN-13, provenance, contrôle qualité, données simulées non exposées |
| `test_api.py` | catalogue, recherche tolérante, dosages jamais substitués, pharmacies |
| `test_nlp.py`, `test_chat.py` | langue, intentions, entités, réponses du chatbot, contexte transmis |
| `test_vision.py`, `test_vision_tesseract.py` | validation des fichiers, qualité, codes-barres, extraction, rapprochement, OCR réel |

### Résultats des exécutions
| Date | Environnement | Résultat |
|---|---|---|
| 09/11/2026 | poste Windows, Python 3.11, PostgreSQL 16 (Docker) | `npx tsc --noEmit` sans erreur ; import de l'API OK ; pytest : 41 tests réussis, 1 ignoré, puis arrêt de Docker Desktop (disque du poste saturé) : les tests suivants n'ont pas pu se connecter à la base. **Suite complète à relancer.** |
| 27/10/2026 | Python 3.11.9, PostgreSQL 16 | `65 passed, 6 skipped` (les 6 tests Tesseract ignorés : OCR absent du poste) |
| 26/10/2026 | Python 3.11.9, PostgreSQL 16.15 | `34 passed` ; `alembic upgrade/downgrade/check`, `quality --strict` OK |

Vérifications fonctionnelles du 09/11/2026 sur l'API locale (OCR Tesseract 5.4 actif dans le conteneur) :
- chatbot : « Quels sont les dosages disponibles pour AMLOR ? » (fr, `dosages`), question arabe sur la substance
  active (ar, `active_ingredient`), « Ch7al taman dyal AMLOR 5 mg ? » (`darija_latin`, `price`, prix absent annoncé),
  pharmacies de garde à Casablanca (`on_duty`, aucune garde vérifiée annoncée) ;
- intégration : avec le contexte AMLOR 5 MG, « Quelle est la substance active de ce médicament ? » → AMLODIPINE (5 MG) ;
- catalogue : « AMLORR 5mg » → AMLOR 5 MG ; « AMLOR 20 mg » → aucun résultat, 5 et 10 mg proposés ;
- pharmacies : Casablanca + « Dounia » → 1 pharmacie ; « XYZ123 » → aucun résultat.

---

## 8. Sources de données, couverture et limites

### Sources réellement intégrées
| Source | Ce qui est chargé | Statut |
|---|---|---|
| AMMPS — base des médicaments | échantillon **transcrit à la main** (page 1, 12 présentations), `data/samples/` | `official` |
| AMMPS — Répertoire des génériques (projet janv. 2026) | extrait de 28 lignes : équivalences réglementaires, EAN-13 | `official` |
| AMMPS — base des pharmacies | 20 pharmacies (nom et ville uniquement) | `official` |
| BDPM (France), Licence Ouverte 2.0 | termes de substances uniquement (aucune présentation ni aucun prix français) ; fichier à télécharger | `reference` |
| Démonstration | 8 médicaments, 9 pharmacies, stocks et gardes **fictifs**, `data/demo/` ; masqués par défaut dans l'API | `simulated` |

### Importeurs prêts mais sans données chargées
CNOPS 2014 (data.gov.ma, indisponible en HTTP 503 lors de la vérification), OpenStreetMap, gardes de pharmacies,
interactions (DDInter), rubriques RCP, corpus de photos. Ces sources **ne sont pas intégrées** à la base livrée.

### Couverture (base locale, 09/11/2026)
42 spécialités (34 officielles, 8 simulées), 46 présentations, 23 EAN-13 valides, 29 pharmacies (20 du registre AMMPS),
8 groupes génériques, 0 section clinique. À comparer aux **9 936 fiches** et **8 951 pharmacies** publiées par l'AMMPS :
**la base ne contient qu'une petite partie des médicaments marocains** ; beaucoup de recherches répondront
« introuvable ». Seules 6 présentations officielles portent un prix PPV.

### Données non publiées dans ce dépôt
- L'export complet de l'AMMPS n'existe pas publiquement et son site indique « tous droits réservés » : aucun scraper
  n'est fourni ; un chargement complet suppose un export obtenu auprès de l'AMMPS (`import-ammps`).
- Le fichier BDPM (`data/raw/`, non versionné) se télécharge librement (voir 5.6).
- Aucune photo de boîte ni aucun dump de base n'est publié ; la base se reconstruit avec `alembic upgrade head` + `seed`.

### Limites du prototype
- Lexiques NLP écrits à la main : couverture partielle de la darija et de l'arabizi ; pas de modèle appris.
- Pill Identifier : seuils heuristiques, non calibrés sur un corpus de photos réelles ; l'indice 0-100 sert à classer
  et à expliquer, ce n'est ni une probabilité ni une précision mesurée ; aucun réseau de neurones entraîné.
- La présentation exacte d'une boîte peut rester non confirmée (exemple : AMLOR 5 mg, boîtes de 28 et 14 à égalité).
- Aucune garde de pharmacie vérifiée ; stock jamais présenté comme vérifié.
- Le numéro du Centre Anti-Poison (`POISON_CENTER`) provient d'une source de 2013-2014 : à revérifier.

### Règles de fiabilité
- Aucun prix, stock, adresse, interaction ou texte clinique n'est inventé ; une donnée absente s'affiche comme absente.
- Les prix CNOPS (2014) ne remplacent jamais les prix AMMPS et ne sont jamais présentés comme prix courants.
- Les sources étrangères n'enrichissent que la terminologie ; aucune donnée d'un autre marché n'entre dans le catalogue.
- Confidentialité : le texte des messages n'est pas conservé (analyse seule, 72 h) ; les photos sont traitées en
  mémoire, jamais envoyées à un service externe, et seule leur empreinte SHA-256 est conservée (24 h).

---

## 9. Documentation détaillée
| Fichier | Contenu |
|---|---|
| `docs/CHATBOT.md` | pipeline NLP, intentions, contexte, règles de sécurité |
| `docs/PILL_IDENTIFIER.md` | pipeline vision, indice de correspondance, règles de décision, corpus, installation de Tesseract |
| `docs/API.md` | référence des endpoints |
| `docs/DATA_SOURCES.md` | sources vérifiées, licences, limites |
| `docs/DATA_PIPELINE.md` | principes, commandes d'import, modèle de données, contrôle qualité |
| `docs/DEMO.md` | scénario de démonstration |
| `data/README.md` | organisation des fichiers de données |

---

**Auteurs :** Hafsa Benabou · Khalid Elharmoud — ChallengeCamp Data Science, INPT Rabat, 2026.
