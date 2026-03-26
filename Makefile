.DEFAULT_GOAL := help

.PHONY: help install run test lint format docs hooks

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'

install: ## Install all dependencies
	uv sync --all-groups

hooks: ## Install pre-commit hooks
	uv run pre-commit install

run: ## Run the Streamlit app
	uv run streamlit run app/app.py

test: ## Run tests with coverage
	uv run pytest --cov

lint: ## Check code style
	uv run ruff check src/ app/

format: ## Format code
	uv run ruff format src/ app/

docs: ## Serve documentation locally
	uv run mkdocs serve
