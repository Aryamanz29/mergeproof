.PHONY: help setup lint fmt typecheck test integration check docs docs-serve diagrams screenshots schema build clean

help:            ## show this help
	@grep -E '^[a-z]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## /\t/' | column -t -s "$$(printf '\t')"

setup:           ## create the virtualenv, install everything, install git hooks
	uv sync --group dev
	uv pip install -e examples/plugins/mergeproof-langfuse -e examples/plugins/mergeproof-braintrust
	uv run pre-commit install --install-hooks

lint:            ## ruff + format check
	uv run ruff check .
	uv run ruff format --check .

fmt:             ## rewrite files with ruff
	uv run ruff check --fix .
	uv run ruff format .

typecheck:       ## mypy over src
	uv run mypy

test:            ## unit tests with coverage
	uv run pytest tests/unit --cov --cov-report=term-missing

integration:     ## drive the installed CLI, examples and plugin
	uv run pytest tests/integration examples/plugins/*/tests -m "integration or not integration"

check:           ## run this repository's own gate against the working tree
	uv run mergeproof check --local

docs:            ## build the documentation site into site/
	uv run --group docs mkdocs build --strict

docs-serve:      ## serve the documentation with live reload
	uv run --group docs mkdocs serve

diagrams:        ## render docs/diagrams/*.d2 to docs/assets (needs d2: brew install d2)
	for f in docs/diagrams/*.d2; do d2 $$f docs/assets/$$(basename $${f%.d2}).svg; done

screenshots:     ## re-shoot the README pictures from live output (needs gh and Chrome)
	uv run scripts/screenshots comment 33
	uv run scripts/screenshots explain examples/python-library missing-tests

schema:          ## regenerate docs/schema/mergeproof-v1.json from the models
	uv run mergeproof schema > docs/schema/mergeproof-v1.json

build:           ## sdist + wheel into dist/
	uv build

clean:
	rm -rf dist build site .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
