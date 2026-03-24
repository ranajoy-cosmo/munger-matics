.DEFAULT_GOAL := help

.PHONY: help install run test lint format

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'

install: ## Install all dependencies
	uv sync --all-groups

run: ## Run the Streamlit app
	uv run streamlit run app/app.py

test: ## Run tests
	uv run pytest tests/

lint: ## Check code style
	uv run ruff check src/ app/

format: ## Format code
	uv run ruff format src/ app/
