.PHONY: setup setup-models test lint kb-ingest db-up db-down db-reset seed

setup:
	poetry install

setup-models:
	poetry run python -m spacy download es_core_news_sm

test:
	poetry run pytest tests/ -v

lint:
	poetry run ruff check src/

kb-ingest:
	poetry run python -m aegis.kb.cli ingest --sources data/sources

db-up:
	docker compose up -d

db-down:
	docker compose down

db-reset:
	docker compose down -v && docker compose up -d --wait

seed:
	docker compose exec -T db psql -U aegis -d aegis_finance -f /docker-entrypoint-initdb.d/003_seed_synthetic.sql
