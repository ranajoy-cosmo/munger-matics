# Roadmap

This document describes the five planned phases of Munger-Matics. Each phase has a defined scope,
entry criteria, and exit criteria (definition of done). Phases are sequential — later phases depend
on data and infrastructure from earlier ones.

---

## Phase 1 — Financial Ledger

**Entry criteria:** None. This is where development begins.

**Goal:** Establish the data foundation. The user can get all their transactions into the system,
categorise them, and see a basic picture of their spending.

### Scope

**Accounts**
- Add an account (name, type, institution, opening balance, currency)
- Edit account details
- Deactivate an account (soft delete — transactions are preserved)
- View all accounts with computed current balance

**CSV Import**
- Upload a CSV file from any bank or broker
- Map CSV columns to the standard fields: date, amount, description
- Preview parsed rows before confirming import
- Detect and skip duplicate transactions (hash-based deduplication)
- Save column mapping per institution so it is reused on the next import
- Institution mappings stored in `config/csv_mappings.toml`

**Manual Entry**
- Add a single transaction manually (account, date, amount, description, category)

**Categories**
- Seed default two-level hierarchy on first run (see [Data Model](data-model.md) for full list)
- Add custom subcategories under any top-level category
- Rename categories

**Category Rules**
- Add a rule: pattern + match type (contains / starts\_with / regex) → category
- Rules are applied automatically at import time
- Re-run rules against all uncategorised existing transactions
- User correction to a transaction category can optionally be saved as a new rule

**Transaction Ledger**
- View all transactions, filterable by: account, date range, category, source
- Edit category inline
- Add notes to a transaction
- Mark two transactions as a transfer (links them, excludes both from income/expense totals)

**Dashboard**
- Account balances overview
- Current month: total income, total expenses, net
- Top 5 expense categories this month (bar chart)
- Month selector to view any past month

**Exit criteria (definition of done):**

- [ ] Import 3 months of transactions from 2 different bank CSVs with zero manual re-entry
- [ ] All transactions have a category (via rules, auto-categorisation, or manual assignment)
- [ ] Re-importing the same CSV produces zero new rows
- [ ] Dashboard shows correct income, expenses, and balances
- [ ] All Phase 1 tests pass

---

## Phase 2 — Budgeting

**Entry criteria:** At least 1 month of clean, fully categorised transaction data from Phase 1.

**Goal:** The user can plan their spending, measure against the plan, and identify trends.

### Scope

- Create a monthly budget envelope per expense category (amount, month)
- Copy last month's budget as a starting point for this month
- Budget vs actual dashboard: for each category, show budgeted / spent / remaining
- Visual over-budget indicator (colour coding)
- 3/6/12-month rolling spending trend per category
- Detect recurring transactions (same merchant, similar amount, monthly or weekly pattern)
- Flag unbudgeted categories that had spending this month

**Exit criteria:**

- [ ] Set a budget for all expense categories for the current month
- [ ] Budget vs actual dashboard reflects real transaction data
- [ ] Recurring transactions are automatically flagged

---

## Phase 3 — Net Worth & Investments

**Entry criteria:** Investment and/or retirement accounts added in Phase 1.

**Goal:** The user has a single net worth figure that includes cash, investments, and retirement,
updated at least monthly.

### Scope

- Portfolio holdings entry: upload broker CSV (ticker, quantity, purchase price, date)
- Security price refresh: manual price entry or CSV from broker
- Net worth calculation: (cash account balances + investment market value + retirement balance) − (credit card balances + loan balances)
- Net worth timeline: monthly snapshot chart
- Simple investment return calculation (XIRR) per holding and overall portfolio
- Dividend and capital gains income automatically attributed to Investment Income category

**Exit criteria:**

- [ ] Net worth figure visible on dashboard, updated from latest account and portfolio data
- [ ] Net worth has at least 3 monthly data points for the timeline chart

---

## Phase 4 — Future Planning

**Entry criteria:** At least 3 months of transaction data (for savings rate calculation) and a net
worth baseline from Phase 3.

**Goal:** The user can answer concrete financial planning questions: how long to save for a house,
whether the savings rate is sufficient, and what retirement looks like under different assumptions.

### Scope

**Savings Rate**
- Calculate actual monthly savings rate: (income − expenses) ÷ income
- Rolling 3/6/12-month average
- Target savings rate input with progress indicator

**House Deposit Goal**
- Create a savings goal: name, target amount, target date
- Show progress: current amount, amount remaining, projected completion date at current savings rate
- "What if I save €X more per month?" sensitivity analysis

**Home Purchase Affordability Model**

Inputs (user-controlled):
- Target property price (€)
- Down payment percentage (default: 20%)
- Mortgage interest rate (%)
- Loan term (years)
- Estimated annual property costs (taxes, insurance, maintenance)

Outputs:
- Required down payment amount
- Estimated monthly mortgage payment (principal + interest)
- Total monthly housing cost (mortgage + property costs ÷ 12)
- Debt-to-income ratio (DTI)
- Months until down payment is saved at current savings rate
- Housing cost as % of gross monthly income (28% rule indicator)

The model applies the EU standard: no PMI, 15–25% down payment typical, fixed or variable rate.

**Retirement Projection**

Inputs:
- Current age and target retirement age
- Current total savings and investments (pulled from Phase 3 net worth)
- Annual contribution (pulled from Phase 1 savings rate)
- Expected nominal investment return (default: 6%)
- Expected inflation rate (default: 2.5%)

Outputs:
- FIRE number: annual retirement expenses × 25 (based on 4% safe withdrawal rate)
- Projected portfolio at retirement (compound growth formula)
- Years to FIRE
- Monte Carlo range (10th / 50th / 90th percentile) using ±3% return volatility

**"What If" Scenario Comparison**

Allow the user to define 2–3 scenarios with different values for one variable (e.g. savings rate,
return, retirement age) and see side-by-side outcome comparison.

**Exit criteria:**

- [ ] Home affordability model produces correct payment and DTI outputs for test inputs
- [ ] Retirement projection matches manual calculation for baseline inputs
- [ ] Savings goal shows correct projected completion date based on current savings rate

---

## Phase 5 — Automation

**Entry criteria:** Phases 1–4 stable, tested, and in daily use.

**Goal:** Manual CSV exports are replaced by automatic transaction sync from connected EU banks.

### Scope

- EU open banking integration via Tink (PSD2 AIS)
- OAuth 2.0 consent flow in the Streamlit app
- Prefect flow: daily scheduled transaction pull per connected account
- Token refresh handling (PSD2 requires periodic re-consent, typically 90 days)
- De-duplication against existing transactions (same hash logic as CSV import)
- Category rule application on newly synced transactions
- Weekly email/notification digest: income, expenses, top categories, savings rate

**Fallback:** Salt Edge if a specific institution is not covered by Tink.

**Exit criteria:**

- [ ] At least 2 bank accounts connected and syncing daily without manual intervention
- [ ] New transactions appear within 24 hours of posting
- [ ] Weekly digest shows correct summary figures

---

## What is explicitly not planned

- Tax return preparation
- Shared/household finance management
- Cryptocurrency
- Business accounting
- Mobile app
