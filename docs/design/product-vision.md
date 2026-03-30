# Product Vision

## Vision Statement

Munger-Matics is a self-hosted personal financial intelligence platform. It gives a financially
literate individual in the EU complete, unified visibility into their cash flow, net worth, and
investments — and the forward-looking tools to make confident decisions about major life events
like buying a home and retiring.

---

## User Profile

| Dimension | Detail |
|---|---|
| Location | EU — EUR as base currency |
| Income | Salary + investment income (dividends, capital gains) |
| Assets | Cash accounts, stocks/ETFs, retirement fund, real estate (future) |
| Accounts | 4–8 financial accounts across 1–3 institutions |
| Data ingestion | CSV export from bank/broker portals (primary); manual entry; bank API (later) |
| Current tooling | None — starting from scratch |
| Primary pain | No structured view of finances; flying blind on savings rate and home affordability |

---

## Design Principles

1. **Correctness over convenience.** Financial data must be exact. Monetary values are never
   floats. Rounding rules are explicit and documented. Calculations are testable with concrete
   numeric examples.

2. **Privacy by default.** The application is self-hosted. No telemetry, no third-party data
   sharing, no cloud sync unless the user explicitly configures it.

3. **Explicit over automatic.** The user controls categorisation and rules. Automation assists
   (suggests, pre-fills) but never silently overrides. Every auto-assigned category can be
   corrected and the correction can be turned into a rule.

4. **Build on data.** Every planning and projection feature requires real historical data to be
   meaningful. Planning tools are gated on having at least one full month of clean transaction
   data.

---

## Core Use Cases

| ID | Use Case | Phase |
|---|---|---|
| UC1 | See all account balances and total net worth at a glance | 1 |
| UC2 | Understand where money went this month, broken down by category | 1 |
| UC3 | Import transactions from a bank CSV without manual re-entry | 1 |
| UC4 | Track monthly spending against a budget per category | 2 |
| UC5 | See current net worth (cash + investments + retirement − liabilities) and how it has changed | 3 |
| UC6 | Know whether my savings rate is on track to reach my house deposit by a target date | 4 |
| UC7 | Model how long until a target property price is affordable given current savings rate | 4 |
| UC8 | Project retirement savings under different contribution and return assumptions | 4 |

---

## Feature Phases

### Phase 1 — Financial Ledger
*The data foundation. Nothing else is meaningful without this.*

- Account management: add, edit, and deactivate accounts (bank, savings, investment, retirement, credit card, loan)
- CSV import wizard: upload → map columns → preview → confirm
- Manual transaction entry
- Transaction deduplication (safe to re-import the same CSV)
- Category hierarchy: seeded defaults + user-defined additions
- Category rules: pattern-matching engine to auto-categorise on import
- Transaction ledger with filtering by account, date range, and category
- Monthly income vs expenses summary
- Spending by category chart
- Account balances overview

### Phase 2 — Budgeting
*Entry criteria: at least one month of clean transaction data.*

- Monthly budget envelopes per category
- Budget vs actual dashboard
- Visual over-budget indicators
- 3/6/12-month spending trends
- Recurring transaction detection

### Phase 3 — Net Worth & Investments
*Entry criteria: investment and retirement accounts added.*

- Portfolio holdings entry via broker CSV
- Security price refresh (manual or price API)
- Net worth calculation: (cash + investments + retirement) − (credit card + loan balances)
- Net worth timeline chart
- Simple return calculation (XIRR)

### Phase 4 — Future Planning
*Entry criteria: ≥3 months of transaction data and a net worth baseline.*

- Savings rate calculator (actual savings ÷ net income)
- House deposit goal tracker: target amount, progress, projected completion date
- Home purchase affordability model (see [Feature Spec: Phase 1](feature-01-ledger.md) for analogous detail)
- Retirement projection: FIRE number, years to FIRE, Monte Carlo scenario view
- "What if" comparisons: change one variable, see the impact on the outcome

### Phase 5 — Automation
*Entry criteria: Phases 1–4 stable and tested.*

- EU open banking integration via Tink (PSD2, 3,400+ banks across 18 EU markets)
- OAuth token management and scheduled transaction sync via Prefect flows
- Frequency-based auto-categorisation improvements
- Weekly digest summary

---

## Success Criteria

| Phase | Definition of Done |
|---|---|
| 1 | Import 3 months of transactions from 2 different bank CSVs; view all spending by category; see each account balance |
| 2 | Set a monthly budget per category and see actual vs planned with visual over/under indicators |
| 3 | View current net worth updated monthly across cash, investments, and retirement accounts |
| 4 | Answer "when can I afford a €400k house if I save X/month at my current spending rate?" |
| 5 | Transactions from at least 2 connected EU banks appear automatically within 24 hours |

---

## Out of Scope

- Tax return preparation or filing
- Shared/household finance management (single user only)
- Cryptocurrency tracking
- Business accounting or invoicing
- Mobile application
