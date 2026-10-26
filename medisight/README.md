# MEDISIGHT — Smart Pharmaceutical Assistant & AI Pill Identifier

Plateforme d'information pharmaceutique pour le Maroc (ChallengeCamp Data Science, INPT) : chatbot multilingue
(français, arabe, darija) et identification de médicaments par photo, sur une base PostgreSQL commune et sourcée.

> MEDISIGHT fournit une information, pas un avis médical. Toute identification par image doit être vérifiée par un pharmacien.

## État d'avancement

| Lot | Contenu | État |
|---|---|---|
| **1. Données** | Schéma PostgreSQL (22 tables, migrations Alembic), importeurs AMMPS / répertoire des génériques / CNOPS / OpenStreetMap / gardes / RCP / interactions, provenance et statuts, échantillons réels, démo simulée, CLI, tests | **Livré et testé** |
| **1 bis. Enrichissement (phase 1)** | Révision 0002 (photos, annotations OCR, variantes de noms, conditionnement, marché des sources) ; répertoire vérifié par dosage et forme ; GTIN-14 ; CNOPS historique uniquement ; terminologie BDPM ; contrôle qualité `quality --strict` ; recherche par code-barres | **Livré et testé** (26/10/2026) |
| 2a. API catalogue | API REST FastAPI : santé, sources, recherche tolérante aux fautes (dosage jamais substitué), fiches, génériques réglementaires vs composition, pharmacies, gardes | **Livré et testé** |
| 2b. NLP + chatbot | Normalisation darija/arabizi, langue, entités, intentions, chatbot | Prochain lot |
| 3. Pill Identifier | Qualité d'image, code-barres EAN-13, OCR Tesseract, caractéristiques visuelles, fusion des indices | À venir |
| 4a. Site web | Next.js 15 + Tailwind : accueil, catalogue avec recherche, fiche médicament (prix sourcés, génériques réglementaires et de composition, informations cliniques), pharmacies et gardes, à propos ; pages Chatbot et Identification décrivant leur état | **Livré et vérifié** |
| 4b. Site (suite) | Chatbot et identification branchés, sélecteur de langue FR/AR/EN, affichage de droite à gauche (RTL) | À venir |
| 5. Intégration | Docker Compose complet, scénarios de bout en bout, documentation finale | À venir |

## Démarrage (lot 1)
```bash
cp .env.example .env
docker compose up -d db                      # ou un PostgreSQL 16 local avec pg_trgm
cd backend && pip install -r requirements-dev.txt
alembic upgrade head
python -m app.ingestion.cli seed             # échantillons officiels + démo simulée
python -m app.ingestion.cli stats
python -m pytest -q                          # crée une base medisight_test dédiée
```

## Voir le site en local (deux terminaux)
Prérequis : base chargée (étapes ci-dessus) et Node.js 20 ou plus récent.

Terminal 1, API :
```bash
cd backend
python -m uvicorn app.main:app --reload --port 8000
```
Terminal 2, site :
```bash
cd frontend
npm install
npm run dev
```
Ouvrir http://localhost:3000. Le site relaie ses appels `/api/*` vers le port 8000 (variable `BACKEND_URL` pour changer).

## Voir l'API dans le navigateur
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```
Puis ouvrir http://localhost:8000/docs (documentation interactive Swagger) — par exemple `GET /api/medicines/search?q=dolipran 500mg`.

## Tests réellement exécutés (26/10/2026, phase 1, PostgreSQL 16.15, Python 3.11.9)
`34 passed` (20 tests existants, dont 3 adaptés aux nouvelles règles, + 14 nouveaux dans `tests/test_data_quality.py`) : découpage
des libellés du répertoire ancré sur le groupe (FUSIDATE PHARMA 5 2 %), équivalence de dosages sans confusion (concentration ≠ dose,
« 0,02 » = « 2 % »), membres de dosage ou de forme différents non rattachés, GTIN-14, conditionnement non deviné, ligne simulée
refusée sur une fiche officielle, BDPM limitée aux termes de recherche (faux positifs réels écartés), variantes de noms sourcées,
contrôle qualité (0 critique sur le seed, violations provoquées détectées), recherche exacte par code-barres, faute de frappe sans
changement de dosage, marché des sources, prix minimal sans présentation simulée.
Également vérifiés : `alembic upgrade` 0001 → 0002, `downgrade` puis `upgrade` sur une base déjà remplie (aucune ligne perdue),
`alembic check` (modèle et migrations synchronisés), import du vrai `CIS_COMPO_bdpm.txt` (32 439 lignes, deux passages),
`quality --strict` (code de sortie 0), API lancée avec uvicorn (santé, sources, recherche, code-barres, autocomplétion, fiche,
génériques, `/docs`). Non exécutés : import CNOPS réel (data.gov.ma en HTTP 503), `next build` (frontend non modifié).

## Tests exécutés précédemment (25/10/2026, PostgreSQL 16.15, Python 3.12)
`20 passed` (12 données + 8 API). Données : parsing des prix (formats AMMPS), dosages multiples et concentrations, formes canoniques, validation EAN-13,
jointure AMMPS × répertoire (prix + code-barres sur la même présentation), rejet des anomalies d'origine, idempotence,
étiquetage et purge des données simulées, non-écrasement d'un prix AMMPS 2026 par un prix CNOPS 2014, extraction de rubriques
RCP depuis un PDF, rejet des substances inconnues dans les interactions, import OpenStreetMap (ville déduite, rapprochement
avec le registre AMMPS), validation des gardes. API : correction de « dolipran 500mg » sans changer le dosage, aucun dosage substitué (« doliprane 750 mg » → dosages disponibles proposés), recherche insensible aux accents, provenance des prix, séparation génériques réglementaires / composition, stock jamais présenté comme vérifié, erreur 503 si la base est indisponible.

Site (25/10/2026) : `next build` sans erreur (9 routes) ; les 8 pages répondent en 200 avec l'API lancée ; via le proxy du site, « dolipran 500mg » renvoie Doliprane 500 mg, « doliprane 750 mg » ne renvoie rien et propose 500 et 1000 mg, A.V.T. affiche prix AMMPS et EAN-13, Casablanca liste la pharmacie du registre AMMPS et les pharmacies fictives marquées comme telles. Non vérifié automatiquement : le rendu visuel dans un navigateur et l'affichage du message d'erreur quand l'API est arrêtée.

## Règles de fiabilité appliquées dès ce lot
- Chaque valeur porte sa source, sa date de version et un statut : `official`, `reference`, `unverified` ou `simulated`.
- Aucun prix, stock, adresse, interaction ou texte clinique n'est inventé ; les données de démonstration sont marquées `simulated` et supprimables (`purge-simulated`).
- Les prix CNOPS (2014) ne remplacent jamais les prix AMMPS (base mise à jour le 01/10/2026) et ne sont jamais présentés comme prix courants (valeurs historiques datées dans `reimbursements`).
- Les sources étrangères (BDPM, France) n'enrichissent que la terminologie des substances ; aucune présentation ni aucun prix étranger.
- `python -m app.ingestion.cli quality --strict` contrôle ces règles après chaque import.
- Pas de collecte automatisée du site AMMPS (« tous droits réservés ») sans autorisation : import d'exports ou saisie manuelle.

## Documentation
- `docs/DATA_SOURCES.md` — sources vérifiées, licences, limites
- `docs/DATA_PIPELINE.md` — principes, commandes, modèle, résultats du chargement
- `data/README.md` — organisation des fichiers de données
