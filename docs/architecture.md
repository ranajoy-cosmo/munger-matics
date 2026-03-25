# Architecture

## Project Structure

```
munger-matics/
├── src/munger_matics/   # core package — business logic and data layer
├── app/                 # Streamlit dashboard (presentation layer)
│   └── pages/           # multi-page app structure
├── tests/               # mirrors src/ structure
├── notebooks/           # exploratory analysis only
├── data/
│   ├── raw/             # source data, never modified
│   └── processed/       # derived outputs
├── flows/               # Prefect orchestration
├── config/              # business configuration (committed)
└── scripts/             # one-off utility scripts
```

---

## Key Design Decisions

### `src/` layout

The core package lives in `src/munger_matics/` rather than at the root. This enforces that the package must be installed before it can be imported, which catches packaging issues early and prevents accidental imports of uninstalled code.

### Dashboard lives outside `src/`

`app/` is a presentation layer, not business logic. Keeping it separate from `src/` makes the boundary explicit: the dashboard depends on the core package, never the other way around. The core package must be usable without Streamlit.

### `data/` is gitignored

`data/raw/` and `data/processed/` are excluded from version control. This directory will contain personal financial data (bank statements, transaction exports) that must never be committed. The directory structure itself is tracked via `.gitkeep` files so it is preserved without the contents.

### `config/` vs `.env`

Two separate concerns:

- `.env` — secrets and environment-specific values (never committed)
- `config/` — business configuration such as budget categories, account mappings, spending thresholds (committed, versioned)

### Notebooks are exploration only

`notebooks/` is for investigation and prototyping. No application code may import from notebooks. Useful logic discovered in a notebook must be promoted to `src/` before it can be used by the app.

### `flows/` not `prefect/`

The orchestration directory is named after what it does, not the tool used to do it. This keeps the mental model clean if the orchestration layer ever changes.

---

## Technology Choices

| Tool | Role | Why |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | Environment & dependency management | Fast, modern, single tool for venv + packages + lockfile |
| [Polars](https://docs.pola.rs/) | Data manipulation | Faster than Pandas, expressive API, strong typing |
| [Streamlit](https://streamlit.io/) | Dashboard | Low-friction Python-native UI, no frontend knowledge required |
| [Prefect](https://www.prefect.io/) | Orchestration | Manages scheduled and triggered data pipelines |
| [Ruff](https://docs.astral.sh/ruff/) | Linting & formatting | Replaces Flake8 + Black + isort in a single fast tool |
| [pytest](https://pytest.org/) | Testing | Standard, well-supported Python test framework |
| [MkDocs Material](https://squidfunk.github.io/mkdocs-material/) | Documentation site | Markdown-based, Python-native, deploys to GitHub Pages |
