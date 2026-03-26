# CLAUDE.md

Instructions and context for Claude Code. Read this before every session.

---

## Project

Personal accounting, budgeting and financial planning application. Python backend for data processing and financial logic. Streamlit dashboard as the frontend. Prefect for scheduled data pipelines.

**Docs site:** https://ranajoy-cosmo.github.io/munger-matics/

---

## Stack

| Layer | Tool |
|---|---|
| Environment | uv (`src/` layout) |
| Data & logic | Python 3.12 + Polars |
| Validation | Pydantic v2 |
| Dashboard | Streamlit (multi-page) |
| Orchestration | Prefect (`flows/` group) |
| Linting | Ruff |
| Type checking | mypy (loose — tighten gradually) |
| Testing | pytest + pytest-cov |
| Docs | MkDocs + Material |

---

## Project Structure

```
src/munger_matics/   # core package — business logic, data layer
app/                 # Streamlit dashboard (presentation layer only)
  pages/             # Streamlit multi-page structure
tests/               # mirrors src/ structure exactly
notebooks/           # exploration only — never imported by src/
data/
  raw/               # never modified — gitignored
  processed/         # derived outputs — gitignored
flows/               # Prefect orchestration
config/              # business config committed to git
scripts/             # one-off utilities
docs/                # MkDocs source
```

---

## Conventions

### Commits

Conventional Commits with ALL CAPS types:

```
TYPE(scope): short description

[optional body — explain why, not what]
```

Types: `FEAT`, `FIX`, `CHORE`, `REFACTOR`, `TEST`, `DOCS`, `DATA`, `FLOW`

Examples:
```
FEAT(budget): add monthly allocation model
FIX(dashboard): correct currency formatting on negative values
CHORE(deps): update polars
```

Rules: imperative mood, subject under 72 chars, one concern per commit.

### Branches

GitHub Flow. Branch prefixes: `feature/`, `fix/`, `chore/`, `refactor/`, `test/`, `docs/`, `data/`, `flow/`

Never commit directly to `main`.

### Dependencies

```bash
uv add some-package              # runtime
uv add --group dev some-tool     # dev only
```

Always commit `uv.lock` after changes.

---

## Guardrails

### Never do these without being asked

- Do not add docstrings, comments, or type annotations to code that wasn't changed
- Do not refactor surrounding code when fixing a specific bug
- Do not add error handling for scenarios that cannot happen
- Do not create helper abstractions for one-off operations
- Do not add features beyond what was explicitly requested
- Do not commit — propose the commit message and wait for confirmation
- Do not push to remote — ever, unless explicitly instructed

### Code quality

- Run `make lint` and `make typecheck` mentally before proposing code — don't write code that will obviously fail them
- Do not suppress mypy or ruff errors with `# type: ignore` or `# noqa` without explaining why
- Keep functions small and single-purpose
- Prefer explicit over clever

### Financial logic — treat with extra care

This application handles personal financial data. Errors in financial logic are silent and damaging.

- Flag any assumption made about rounding, precision, or currency handling
- Do not write aggregation or calculation logic without stating the expected behaviour explicitly in a comment or test
- Prefer `Decimal` over `float` for any monetary value
- When writing financial functions, always propose a corresponding test with concrete numeric examples
- Never simplify financial logic for brevity — correctness takes precedence

### Architecture boundaries

- `app/` depends on `src/` — never the reverse
- `notebooks/` may import from `src/` — `src/` never imports from notebooks
- `config/` contains committed business config — secrets belong in `.env` only
- `data/` contents are never committed — personal financial data

---

## Working Style

- **Propose before implementing** for any change affecting more than one file or touching architecture
- **Small tasks over large ones** — one concern per session keeps diffs reviewable
- **Ask when requirements are ambiguous** — especially for financial logic, assumptions are dangerous
- **Read files before editing them** — don't suggest changes to code that hasn't been read
- **Flag surprises** — if something unexpected is found while working, surface it before continuing
