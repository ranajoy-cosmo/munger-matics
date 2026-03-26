# Getting Started

## Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/) — Python package and environment manager
- Python 3.12 (managed automatically by uv via `.python-version`)

## Installation

```bash
# Clone the repo
git clone https://github.com/ranajoy-cosmo/munger-matics.git
cd munger-matics

# Install runtime + dev dependencies
make install

# Install pre-commit hooks
make hooks
```

## Environment Variables

Create a `.env` file in the project root and fill in your values. Never commit `.env`.

## Running the App

```bash
make run
```

This starts the Streamlit dashboard at `http://localhost:8501`.

## Common Commands

| Command | Description |
|---|---|
| `make install` | Install all dependencies |
| `make hooks` | Install pre-commit hooks |
| `make run` | Run the Streamlit dashboard |
| `make test` | Run tests with coverage report |
| `make lint` | Check code style |
| `make typecheck` | Run mypy type checking |
| `make format` | Auto-format code |
| `make format-check` | Check formatting without modifying (used in CI) |
| `make docs` | Serve documentation locally at `http://127.0.0.1:8000` |

## Dependency Groups

Dependencies are split into groups in `pyproject.toml`:

- **`[project] dependencies`** — runtime deps, always installed
- **`[dependency-groups] dev`** — development tools (pytest, ruff, mypy, mkdocs-material, pre-commit)
- **`[dependency-groups] flows`** — Prefect orchestration, installed only when working on pipelines

```bash
# Add a runtime dependency
uv add some-package

# Add a dev-only dependency
uv add --group dev some-tool

# Install the flows group to work on Prefect pipelines
uv sync --group flows
```

Always commit `uv.lock` after adding or updating dependencies.
