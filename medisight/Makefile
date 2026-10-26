.PHONY: db migrate seed test stats
db:      ; docker compose up -d db
migrate: ; cd backend && alembic upgrade head
seed:    ; cd backend && python -m app.ingestion.cli seed
test:    ; cd backend && python -m pytest -q
stats:   ; cd backend && python -m app.ingestion.cli stats
