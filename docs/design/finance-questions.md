# Financial Questions — Algorithm Map

This document maps the financial questions a user of this application might ask to the
library functions that answer them. It is the primary reference for prioritising missing
functions and planning dashboard features.

**Status key**

| Symbol | Meaning |
|--------|---------|
| ✅ | Single function call |
| 🔗 | Compose two or more existing functions |
| ⚠️ | Gap — function missing from library |
| 📊 | Ledger/aggregation — answered by the data layer, not the finance library |

**Current public API** (`from munger_matics.finance import …`)

`future_value_simple` · `future_value_compound` · `present_value` · `required_rate` ·
`years_to_target` · `payment` · `pv_annuity` · `fv_annuity` · `periods_to_target` ·
`annuity_required_rate` · `amortization_schedule` · `effective_annual_rate` ·
`nominal_from_ear` · `real_rate` · `cagr` · `npv` · `irr` · `xirr` · `CompoundingFreq` ·
`AmortizationRow`

---

## 1. Day-to-day cash

All of these are ledger aggregation questions. The finance library has no role.
Answers come from grouping and summing transaction data.

| Question | Status | Notes |
|----------|--------|-------|
| Am I spending more than I earn this month? | 📊 | `sum(amounts) by month` |
| Which category is over budget? | 📊 | `actual vs budget by category` |
| Average monthly spend, this year vs last year | 📊 | Rolling 12-month aggregation |
| What recurring charges am I paying? | 📊 | Pattern-match on `description` |
| Is this transaction a duplicate? | 📊 | Matched by `import_hash` at import time |

---

## 2. Debt

### How much interest will this loan cost over its lifetime? 🔗

```
schedule = amortization_schedule(principal, annual_rate, years, freq)
total_interest = sum(row.interest_payment for row in schedule)
```

Equivalent shortcut (no schedule needed):
```
total_interest = payment(principal, annual_rate, years, freq) * n_periods - principal
```

---

### Am I paying down principal or mostly interest at a given point? ✅

```
schedule = amortization_schedule(principal, annual_rate, years, freq)
row = schedule[current_period - 1]
interest_fraction = row.interest_payment / row.payment
```

---

### If I pay €X/month extra, how many months do I save? ⚠️

Requires `payoff_periods(principal, annual_rate, pmt, freq) -> int`.

Formula: $n = -\ln(1 - rP/PMT) / \ln(1+r)$ where $r$ is the periodic rate.

```
# Once implemented:
n_original = payoff_periods(principal, rate, payment(...), freq)
n_overpay  = payoff_periods(principal, rate, payment(...) + overpayment, freq)
months_saved = n_original - n_overpay
```

This function appears in **three** separate question chains (overpayment, consolidation,
fixed vs variable) and is the highest-priority gap in the debt module.

---

### Should I overpay the mortgage or invest the difference? 🔗

```
# Interest saved by overpaying
schedule_normal    = amortization_schedule(principal, mortgage_rate, years, freq)
schedule_overpay   = amortization_schedule(principal, mortgage_rate, remaining_years_after_payoff, freq)
# Note: requires payoff_periods ⚠️ to know when to stop

# Opportunity cost of not investing
investment_fv = fv_annuity(overpayment_amount, investment_rate, years, freq)

# Decision: investment_fv > interest_saved → invest wins
```

**Flag:** this comparison must use after-tax rates on both sides.
Mortgage interest relief and investment tax (e.g. PFU 30% in France) can flip the result.

---

### What do I save by consolidating two loans? 🔗

```
interest_1       = sum(row.interest_payment for row in amortization_schedule(p1, r1, y1, freq))
interest_2       = sum(row.interest_payment for row in amortization_schedule(p2, r2, y2, freq))
interest_merged  = sum(row.interest_payment for row in amortization_schedule(p1+p2, new_rate, new_years, freq))
saving = (interest_1 + interest_2) - interest_merged
```

**Warning:** a longer new term can reduce monthly payments while *increasing* total
interest. Always surface both `monthly_saving` and `total_interest_saving` in the UI.

---

### Fixed vs variable mortgage — which costs less under a rate scenario? 🔗

Run the schedule in segments, one per rate period:

```
# Phase 1: first 3 years at teaser rate
s1 = amortization_schedule(principal, initial_rate, 3, MONTHLY)
balance_after_p1 = s1[-1].remaining_balance

# Phase 2: remaining 22 years at risen rate
s2 = amortization_schedule(balance_after_p1, risen_rate, 22, MONTHLY)

total_variable_cost = sum(r.payment for r in s1) + sum(r.payment for r in s2)
total_fixed_cost    = sum(r.payment for r in amortization_schedule(principal, fixed_rate, 25, MONTHLY))
```

---

### If rates rise 1%, what is my new monthly payment? ✅

```
balance = amortization_schedule(principal, current_rate, years, MONTHLY)[current_period - 1].remaining_balance
new_pmt = payment(balance, current_rate + Decimal("0.01"), remaining_years, MONTHLY)
increase = new_pmt - current_pmt
```

---

## 3. Savings goals

### Will I reach my target before a deadline? 🔗

Both the existing balance (compounding lump sum) and the ongoing contributions
(annuity stream) must be included. Omitting the first term is a common modelling error.

```
fv_existing      = future_value_compound(current_balance, rate, years, freq)
fv_contributions = fv_annuity(monthly_saving, rate, years, freq)
fv_total         = fv_existing + fv_contributions
reached          = fv_total >= target
```

---

### How much must I save each month to reach a target? ⚠️

Requires `sinking_fund_payment(target_fv, annual_rate, years, freq) -> Decimal`.

Formula: $PMT = FV \cdot \frac{r}{(1+r)^n - 1}$

This is the most common personal planning question ("how much do I need to save?")
and is the second-highest priority gap in the library.

```
# Once implemented:
monthly_saving = sinking_fund_payment(target_fv, rate, years, MONTHLY)
```

---

### If the rate drops 0.5%, how much longer will it take? ✅

```
n_now    = periods_to_target(target, pmt, rate, freq, initial_pv)
n_lower  = periods_to_target(target, pmt, rate - Decimal("0.005"), freq, initial_pv)
extra    = n_lower - n_now   # extra periods
```

---

### When do I hit €40K starting from €10K, saving €300/month? ✅

```
n = periods_to_target(
    target_fv   = Decimal("40000"),
    pmt         = Decimal("300"),
    annual_rate = rate,
    freq        = MONTHLY,
    initial_pv  = Decimal("10000"),
)
target_date = today + relativedelta(months=n)
```

---

### What rate of return do I need on my contributions to reach a target? ✅

```
rate_needed = annuity_required_rate(
    target_fv  = target,
    pmt        = monthly_saving,
    years      = years,
    freq       = MONTHLY,
    initial_pv = current_balance,
)
```

---

## 4. Net worth

| Question | Status | Notes |
|----------|--------|-------|
| What is my net worth today? | 📊 | Sum of all account balances |
| Net worth over time | 📊 | Monthly snapshot from ledger |
| Liquid vs illiquid split | 📊 | Account-type aggregation |
| Debt-to-asset ratio | 📊 | `sum(liabilities) / sum(assets)` |

### Am I growing my net worth in real terms? 🔗

```
nominal_growth = cagr(net_worth_start, net_worth_end, years)
real_growth    = real_rate(nominal_growth, avg_annual_inflation)
# real_growth > 0 → gaining purchasing power
# real_growth < 0 → losing purchasing power even if nominally growing
```

---

## 5. Portfolio & investing

### What return have I actually made? ✅

XIRR is the only correct answer when contributions are irregular (which they always are).
CAGR gives a wrong answer here because it ignores *when* money was deployed.

```
# cashflows: each contribution is negative, current portfolio value is final positive
xirr_result = xirr(cashflows, dates)
```

---

### Is my portfolio keeping pace with inflation? 🔗

```
portfolio_return = xirr(cashflows, dates)
real             = real_rate(portfolio_return, avg_annual_inflation)
outpacing        = real > Decimal("0")
```

---

### Am I beating an index fund? 🔗

The only fair comparison feeds the *same cash flows* into the index and measures what
they would be worth.

```
# Reconstruct what the index would have returned on identical investment dates/amounts
index_xirr = xirr(index_equivalent_cashflows, my_dates)
my_xirr    = xirr(my_cashflows, my_dates)
outperforming = my_xirr > index_xirr
```

---

### What was my annualised return over a clean period (no contributions)? ✅

```
annualised = cagr(value_at_start, value_at_end, years)
```

---

## 6. Retirement & long-term planning

### How much do I need saved to sustain a monthly withdrawal? ✅

```
nest_egg = pv_annuity(monthly_withdrawal, return_in_retirement, years_in_retirement, MONTHLY)
```

---

### When can I retire? 🔗

```
nest_egg = pv_annuity(monthly_withdrawal, return_in_retirement, years_in_retirement, MONTHLY)
months   = periods_to_target(nest_egg, monthly_contribution, expected_return, MONTHLY, current_savings)
retirement_date = today + relativedelta(months=months)
```

---

### What is €500K in 30 years worth in today's euros? ✅

`present_value` discounts any future sum back to today. Use inflation as the discount rate:

```
real_value = present_value(Decimal("500000"), inflation_rate, 30, ANNUAL)
```

---

### Retire at 60 vs 65 — what is the real difference? 🔗

```
# Nest egg needed at 60 (more years of retirement to fund)
nest_egg_60 = pv_annuity(monthly_withdrawal, return_in_retirement, life_expectancy - 60, MONTHLY)

# Nest egg needed at 65
nest_egg_65 = pv_annuity(monthly_withdrawal, return_in_retirement, life_expectancy - 65, MONTHLY)

# Extra 5 years of contributions if retiring at 65
extra_pot = fv_annuity(monthly_contribution, expected_return, 5, MONTHLY)

# Net gap: what you need at 60 minus what 5 extra years of saving adds
net_gap = nest_egg_60 - (nest_egg_65 + extra_pot)
```

---

### Six months unpaid leave — what does it cost the retirement pot? 🔗

The true cost is the compounded future value of the missed contributions, not the
face value of the missed payments.

```
missed_face_value = 6 * monthly_contribution
years_to_retirement = ...
cost_at_retirement = future_value_compound(missed_face_value, expected_return, years_to_retirement, MONTHLY)
cost_in_today_euros = present_value(cost_at_retirement, inflation_rate, years_to_retirement, ANNUAL)
```

---

### Move to a lower-paying job — what is the long-run cost? 🔗

```
monthly_shortfall = old_salary - new_salary

# Cost to retirement pot (compounded opportunity cost)
pot_cost = fv_annuity(monthly_shortfall * savings_rate, expected_return, years_to_retirement, MONTHLY)

# Cost in today's money (for human-readable framing)
todays_cost = pv_annuity(monthly_shortfall, discount_rate, working_years_remaining, MONTHLY)
```

---

## 7. Housing

### Can I afford this mortgage? ✅

```
monthly_pmt  = payment(purchase_price - deposit, mortgage_rate, years, MONTHLY)
affordability = monthly_pmt / gross_monthly_income   # should be <= 0.33
```

---

### Buy vs rent — which is cheaper over N years? 🔗

**Ownership cost (net)**
```
schedule        = amortization_schedule(principal, mortgage_rate, N, MONTHLY)
total_paid      = sum(r.payment for r in schedule) + deposit + purchase_costs
equity_at_exit  = projected_property_value - schedule[-1].remaining_balance
net_cost_buy    = total_paid - equity_at_exit
```

**Renting cost (opportunity cost of deposit included)**
```
total_rent        = sum of monthly_rent * 12 across N years (with annual increases)
deposit_invested  = future_value_compound(deposit, investment_rate, N, ANNUAL)
opportunity_cost  = deposit_invested - deposit
net_cost_rent     = total_rent + opportunity_cost
```

**Decision:** `net_cost_buy` vs `net_cost_rent` — lower number wins.

---

### Is it worth overpaying the mortgage in the first 5 years? 🔗

Requires `payoff_periods` ⚠️. Same structure as the general overpayment question in §2.

---

### What is my break-even if I must sell within 3 years? 🔗

```
schedule          = amortization_schedule(principal, rate, 25, MONTHLY)
balance_at_sale   = schedule[35].remaining_balance   # 36th payment = 3 years
total_paid_so_far = payment(...) * 36 + deposit + costs
min_sale_price    = balance_at_sale + total_paid_so_far
```

---

## 8. "What if" scenarios

### How long does my emergency fund last? ✅ (simple case)

Zero-rate assumption (cash held):
```
months = emergency_fund / avg_monthly_burn
```

If the fund is invested:
```
months = periods_to_target(Decimal("0"), avg_monthly_burn, fund_return, MONTHLY, initial_pv=emergency_fund)
```

---

## Gap Summary

The following functions are missing from the library. Both are used repeatedly in the
question chains above.

| Function | Formula | Priority | Used in |
|----------|---------|----------|---------|
| `payoff_periods(principal, annual_rate, pmt, freq)` | $n = -\ln(1 - rP/PMT) / \ln(1+r)$ | **High** | Overpayment analysis, consolidation, fixed vs variable, buy vs rent |
| `sinking_fund_payment(target_fv, annual_rate, years, freq)` | $PMT = FV \cdot r / [(1+r)^n - 1]$ | **High** | Savings planner — the most common personal planning question |

Everything else in this document can be answered by composing the existing public API.

---

## Function Usage Heatmap

Functions that appear in the most question chains, in order:

| Rank | Function | Chains |
|------|----------|--------|
| 1 | `amortization_schedule` | 6 |
| 2 | `payment` | 5 |
| 3 | `fv_annuity` | 4 |
| 4 | `pv_annuity` | 3 |
| 5 | `periods_to_target` | 3 |
| 6 | `xirr` | 3 |
| 7 | `future_value_compound` | 3 |
| 8 | `real_rate` | 3 |
| 9 | `present_value` | 3 |
| 10 | `cagr` | 2 |
| 11 | `annuity_required_rate` | 1 |
| 12 | `future_value_simple` | 0 |
| 13 | `irr` | 0 (subsumed by `xirr`) |
| 14 | `effective_annual_rate` | 0 (rate normalisation, pre-processing) |
| 15 | `nominal_from_ear` | 0 (rate normalisation, pre-processing) |
| 16 | `required_rate` | 0 |
| 17 | `years_to_target` | 0 |

`future_value_simple`, `irr`, `effective_annual_rate`, `nominal_from_ear`, `required_rate`,
and `years_to_target` are correct and well-tested but do not appear directly in
user-facing question chains. They are either used as pre-processing steps
(rate normalisation before passing to other functions) or are edge-case tools. They
should stay in the library for completeness but are low priority for dashboard exposure.
