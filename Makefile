.PHONY: setup setup-models test lint

setup:
	poetry install

setup-models:
	poetry run python -m spacy download es_core_news_sm

test:
	poetry run pytest tests/ -v

lint:
	poetry run ruff check src/
