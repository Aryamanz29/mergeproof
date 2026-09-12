.PHONY: help setup lint fmt typecheck test integration check build clean

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

build:           ## sdist + wheel into dist/
	uv build

clean:
	rm -rf dist build .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
