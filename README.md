# MEDSIGHT — Your Health, Our Intelligence.

Plateforme intelligente d'information pharmaceutique pour le Maroc, réalisée dans le cadre du
**ChallengeCamp Data Science** (INPT, Rabat) par **Hafsa Benabou** et **Khalid Elharmoud**.

Un seul dépôt pour les deux challenges, sur une base PostgreSQL commune :

| Challenge | Contenu | Code |
|---|---|---|
| 1. Chatbot pharmaceutique multilingue | français, arabe, darija ; NLP, entités, réponses sourcées | [`medisight/backend/app/nlp`](medisight/backend/app/nlp), [`medisight/frontend/app/chat`](medisight/frontend/app/chat) |
| 2. Reconnaissance visuelle des médicaments | OpenCV, codes-barres, OCR Tesseract, rapprochement PostgreSQL | [`medisight/backend/app/vision`](medisight/backend/app/vision), [`medisight/frontend/app/identify`](medisight/frontend/app/identify) |

Technologies : Next.js 15, FastAPI, PostgreSQL 16, Docker Compose, Python 3.11, Tesseract OCR, OpenCV.

**Documentation complète, installation et tests : [`medisight/README.md`](medisight/README.md).**

Démarrage rapide :
```bash
git clone https://github.com/hafsa-benabou/MedSight.git
cd MedSight/medisight
cp .env.example .env
docker compose up -d db
cd backend && python -m venv .venv && . .venv/bin/activate      # Windows : .venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m alembic upgrade head && python -m app.ingestion.cli seed
python -m uvicorn app.main:app --reload --port 8000              # puis, dans un autre terminal :
cd ../frontend && npm install && npm run dev                     # http://localhost:3000
```

> MedSight fournit une information, pas un avis médical. Une identification par photo doit être vérifiée par un pharmacien.
