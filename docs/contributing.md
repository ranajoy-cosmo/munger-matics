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

**Examples:**

```
FEAT(budget): add monthly allocation model
FIX(dashboard): correct currency formatting
CHORE(deps): update polars to 1.2.0
TEST(budget): add edge cases for negative balances
DOCS(contributing): add branch naming conventions
DATA(ingest): add CSV import for bank statements
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
make lint      # check for issues
make format    # auto-fix formatting
```

Run both before pushing. CI will fail on lint errors.

## Pre-commit Hooks

Pre-commit hooks run `ruff` automatically on every commit, before the commit lands. This catches lint and formatting issues at the source rather than in CI.

Install the hooks once after cloning:

```bash
make hooks
```

After that, every `git commit` will trigger the checks automatically. If a hook fails, the commit is aborted — fix the issue and commit again.
