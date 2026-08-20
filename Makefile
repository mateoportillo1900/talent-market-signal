# Every command this project needs, discoverable in one place.
#
# `make` on its own lists them. The point is that a new reader should not have
# to reverse-engineer the workflow from a README — the commands are the
# documentation, and they cannot drift from what actually runs.

.DEFAULT_GOAL := help
.PHONY: help install fixture load load-real build check test lint format run explain diagrams clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Install dependencies
	pip install -r requirements-dev.txt

fixture:  ## Generate the synthetic test dataset
	python scripts/make_fixture.py

load:  ## Load the synthetic fixture into Postgres
	python scripts/load_to_postgres.py --fixture

check:  ## Verify the BLS and O*NET source URLs (10s, downloads nothing)
	python scripts/build_dataset.py --check

build:  ## Download the real sources and build the dataset (~10 min)
	python scripts/build_dataset.py

load-real:  ## Load the real dataset into Postgres
	python scripts/load_to_postgres.py

test:  ## Run the test suite
	pytest -q

lint:  ## Check formatting and lint
	ruff check .
	ruff format --check .

format:  ## Apply formatting
	ruff format .
	ruff check --fix .

explain:  ## Print the query plan for every SQL file
	python scripts/explain_queries.py

diagrams:  ## Export the docs' Mermaid diagrams as PNGs
	python scripts/export_diagrams.py

run:  ## Start the dashboard
	streamlit run app.py

clean:  ## Remove caches and generated files
	rm -rf .pytest_cache .ruff_cache data/fixture
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
