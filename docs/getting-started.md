# Getting Started

## Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/) — Python package and environment manager
- Python 3.12 (managed automatically by uv via `.python-version`)

## Installation

```bash
# Clone the repo
git clone https://github.com/ranajoy-cosmo/munger-matics.git
cd munger-matics

# Install all dependencies (runtime + dev)
make install
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
| `make run` | Run the Streamlit dashboard |
| `make test` | Run tests |
| `make lint` | Check code style |
| `make format` | Auto-format code |
| `make docs` | Serve documentation locally at `http://127.0.0.1:8000` |

## Dependency Groups

Dependencies are split into groups in `pyproject.toml`:

- **`[project] dependencies`** — runtime deps, always installed
- **`[dependency-groups] dev`** — development tools only (pytest, ruff, mkdocs-material)

```bash
# Add a runtime dependency
uv add some-package

# Add a dev-only dependency
uv add --group dev some-tool
```

Always commit `uv.lock` after adding or updating dependencies.
