# Contributing

## Environment Setup

This project uses [uv](https://docs.astral.sh/uv/getting-started/installation/) for environment and dependency management.

```bash
# Install all dependencies (runtime + dev)
make install
```

Python version is pinned in `.python-version`. uv handles the interpreter automatically.

### Environment Variables

Copy `.env.example` to `.env` and fill in your values. Never commit `.env`.

```bash
cp .env.example .env
```

---

## Common Commands

| Command | Description |
|---|---|
| `make install` | Install all dependencies |
| `make run` | Run the Streamlit dashboard |
| `make test` | Run tests |
| `make lint` | Check code style |
| `make format` | Auto-format code |

---

## Dependency Groups

Dependencies are split into groups in `pyproject.toml`:

- **`[project] dependencies`** — runtime deps, always installed
- **`[dependency-groups] dev`** — development tools only (pytest, ruff)

```bash
# Add a runtime dependency
uv add some-package

# Add a dev-only dependency
uv add --group dev some-tool
```

Always commit `uv.lock` after adding or updating dependencies.

---

## Branching Strategy

This project follows [GitHub Flow](https://docs.github.com/en/get-started/using-github/github-flow).

**Rules:**
- `main` is always in a runnable state. Never commit directly to it.
- All work happens on short-lived feature branches cut from `main`.
- Open a PR to merge back into `main`. CI must pass before merging.
- Delete the branch after merging.

**Branch naming:**

```
feature/   new functionality          feature/add-budget-model
fix/       bug fixes                  fix/streamlit-crash-on-empty-data
chore/     maintenance, deps, config  chore/update-dependencies
refactor/  restructuring              refactor/extract-calculations
data/      data pipeline work         data/import-csv-parser
flow/      Prefect orchestration      flow/monthly-budget-sync
```

---

## Pull Requests

Even working solo, PRs are the unit of work. A good PR:
- Has a title that completes the sentence *"This PR..."*
- Describes what changed and why, not just what
- Is small and focused — one concern per PR

---

## Code Style

Linting and formatting use [Ruff](https://docs.astral.sh/ruff/).

```bash
make lint      # check for issues
make format    # auto-fix formatting
```

Run both before pushing. CI will fail on lint errors.
