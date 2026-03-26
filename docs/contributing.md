# Contributing

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

## Commit Conventions

This project follows [Conventional Commits](https://www.conventionalcommits.org/).

**Format:**

```
TYPE(scope): short description

[optional body — explain why, not what]
```

**Types:**

| Type | Use for |
|---|---|
| `FEAT` | new feature or capability |
| `FIX` | bug fix |
| `CHORE` | maintenance, deps, config, tooling |
| `REFACTOR` | restructuring without behavior change |
| `TEST` | adding or updating tests |
| `DOCS` | documentation only |
| `DATA` | data pipeline or ingestion work |
| `FLOW` | Prefect orchestration work |

**Examples:**

```
FEAT(budget): add monthly allocation model
FIX(dashboard): correct currency formatting
CHORE(deps): update polars to 1.2.0
TEST(budget): add edge cases for negative balances
DOCS(contributing): add branch naming conventions
DATA(ingest): add CSV import for bank statements
FLOW(budget): add weekly budget sync flow
```

**Rules:**

- Use the imperative mood — "add feature" not "added feature"
- Keep the subject under 72 characters
- The subject says *what*, the body says *why*
- One concern per commit — if you need "and" to describe it, split it

---

## Code Style

Linting and formatting use [Ruff](https://docs.astral.sh/ruff/).

```bash
make lint          # check for lint issues
make format        # auto-fix formatting
make format-check  # check formatting without modifying (what CI runs)
```

Pre-commit hooks auto-fix formatting on every commit. CI enforces both lint and format check on every PR — a PR with either violation will not pass.

## Type Checking

Type checking uses [mypy](https://mypy.readthedocs.io/) with the Pydantic plugin enabled.

```bash
make typecheck
```

Current configuration:
- Missing imports are silenced — many packages don't ship type stubs
- `# type: ignore` comments are kept honest via `warn_unused_ignores`
- Pydantic models are checked via the mypy Pydantic plugin

Stricter settings (`disallow_untyped_defs`, `warn_return_any`) are commented out in `pyproject.toml` and will be enabled gradually as the codebase matures.

CI runs mypy on every PR.

## Pre-commit Hooks

Pre-commit hooks run two checks automatically on every commit:

- `ruff check --fix` — lints and auto-applies safe fixes
- `ruff format` — enforces consistent formatting

This catches and corrects issues before they reach CI. If a hook fails and cannot auto-fix, the commit is aborted — fix the issue and commit again.

Install the hooks once after cloning:

```bash
make hooks
```

After that, every `git commit` will trigger the checks automatically. If a hook fails, the commit is aborted — fix the issue and commit again.
