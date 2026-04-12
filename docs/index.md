# Munger-Matics

A self-hosted personal financial intelligence platform for the financially literate EU individual.
Munger-Matics gives you complete, unified visibility into your cash flow, net worth, and
investments — and the forward-looking tools to make confident decisions about major life events
like buying a home and retiring.

---

## Current status

| Component | Status |
|-----------|--------|
| CCF CSV transaction importer | ✅ Built |
| Finance math library (`munger_matics.finance`) | ✅ Built — 20 functions, 112 tests |
| Database schema (DuckDB) | 🔧 Designed, implementation in progress |
| Account & transaction management | 🔧 In progress (Phase 1) |
| Category rules engine | 📋 Designed |
| Streamlit dashboard | 📋 Designed |
| Budgeting (Phase 2) | 📋 Planned |
| Net worth & portfolio (Phase 3) | 📋 Planned |
| Future planning & projections (Phase 4) | 📋 Planned |

---

## What it will do

**Track** — import bank CSVs, categorise transactions automatically, see exactly where money goes.

**Budget** — set monthly envelopes per category, measure actual vs planned spending.

**Measure** — unified net worth across cash, investments, and retirement accounts.

**Plan** — answer concrete questions: *Can I afford this mortgage? When can I retire? How long
until I reach my house deposit?* Backed by a rigorous financial math library.

---

## Finance math library

The core of the planning and projection features is `munger_matics.finance` — a library of pure
functions for time-value-of-money calculations:

| Module | Functions |
|--------|-----------|
| `compounding` | `future_value_simple`, `future_value_compound`, `present_value`, `required_rate`, `years_to_target` |
| `annuities` | `payment`, `pv_annuity`, `fv_annuity`, `periods_to_target`, `amortization_schedule`, `annuity_required_rate` |
| `rates` | `effective_annual_rate`, `nominal_from_ear`, `real_rate`, `cagr` |
| `cashflows` | `npv`, `irr`, `xirr` |

See [Finance Library](design/finance-library.md) for the full reference.

---

## Stack

| Layer | Tool |
|-------|------|
| Language | Python 3.12 |
| Data & logic | Polars + `decimal.Decimal` |
| Validation | Pydantic v2 |
| Database | DuckDB |
| Dashboard | Streamlit (multi-page) |
| Orchestration | Prefect |
| Environment | uv (`src/` layout) |

---

## Quick links

- [Getting Started](getting-started.md) — set up your environment and run the app
- [Architecture](architecture.md) — project structure and design decisions
- [Contributing](contributing.md) — development workflow, branching and conventions
- [Product Vision](design/product-vision.md) — who this is for and where it's going
- [Roadmap](design/roadmap.md) — the five phases of development
- [Finance Library](design/finance-library.md) — math functions reference
