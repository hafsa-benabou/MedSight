# MEDISIGHT — instructions pour Claude Code

## Projet
Plateforme d'information pharmaceutique pour le Maroc (ChallengeCamp Data Science, INPT).
- `backend/` : API FastAPI + SQLAlchemy 2 + PostgreSQL, pipeline d'import (`app/ingestion`), tests pytest.
- `frontend/` : site Next.js 15 + Tailwind ; appels API via `lib/api.ts` (chemins relatifs `/api/...`).
- `data/` : échantillons officiels transcrits, démo simulée, référentiels, modèles d'import.
- `docs/` : sources de données, pipeline. `README.md` : état d'avancement par lot.

## Environnement (Windows, PowerShell)
- Base : `docker compose up -d db` à la racine. Le service Windows `postgresql-x64-18` doit être arrêté.
- Backend : `cd backend` puis `.venv\Scripts\Activate.ps1`. Toujours lancer les outils via `python -m` (alembic, pytest, uvicorn).
- API : `python -m uvicorn app.main:app --reload --port 8000`. Site : `cd frontend` puis `npm run dev` (http://localhost:3000).
- Vérifications : `python -m pytest -q` dans `backend` (crée une base `medisight_test`) ; `npx next build` dans `frontend`.
- Sous Windows, ne lance pas toi-même de commande shell : écris la commande à exécuter et attends que je te donne le résultat (plantage connu de Claude Code au lancement d'un shell).

## Règles non négociables
1. Ne jamais inventer de donnée pharmaceutique : prix, posologie, effets indésirables, interactions, stock, adresse, garde. Une donnée absente s'affiche comme absente.
2. Chaque donnée garde sa provenance (`source_id`, date de version) et son statut : `official`, `reference`, `unverified` ou `simulated`. Les données de démonstration restent `simulated` et visibles comme telles.
3. Ne jamais remplacer un dosage demandé par un autre. Distinguer l'équivalence réglementaire (Répertoire AMMPS) de la simple correspondance de composition.
4. Pas de collecte automatisée du site de l'AMMPS (« tous droits réservés ») sans autorisation écrite.
5. Toute modification du schéma passe par une migration Alembic (`python -m alembic revision --autogenerate -m "..."`), relue avant `upgrade`.
6. Après chaque modification, lancer les tests concernés. Ne pas annoncer qu'une tâche est terminée si un test échoue.
7. Aucun secret dans le code : utiliser `.env`. Ne pas modifier `.env` sans demande explicite.
8. Messages de sécurité : orienter vers un pharmacien ou un médecin ; urgences SAMU 141, Protection civile 15.

## Conventions
- Python 3.11+, SQLAlchemy 2 (`Mapped`), Pydantic v2. Textes d'interface en français.
- Mettre à jour `README.md` (état d'avancement, tests exécutés) quand une fonctionnalité change.
