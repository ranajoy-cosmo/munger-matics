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

## 9. Tax & net income

| Question | Status | Notes |
|----------|--------|-------|
| What is my effective tax rate this year? | 📊 | `total_tax_paid / gross_income` from ledger |
| Am I using annual tax-free allowances? | 📊 | Compare ledger totals to configured thresholds |

### How much gross do I need to earn to take home a target net salary? ⚠️

Requires a `gross_from_net(net, tax_schedule) -> Decimal` function (or a taxpayer model).
Tax schedules are jurisdiction-specific and change annually — the function must accept a
configurable bracket table rather than hard-coded rates.

---

### How much of a raise actually lands in my pocket? ⚠️

Same dependency as above. Given `old_gross` and `new_gross`, compute:

```
# Once gross_from_net is available:
net_increase = net(new_gross) - net(old_gross)
effective_raise_rate = net_increase / old_net
```

---

## 10. Emergency fund & liquidity

### Do I have enough liquid reserves to cover N months of expenses? 📊 + simple arithmetic

```
monthly_burn = avg_monthly_spend_from_ledger
coverage     = liquid_balance / monthly_burn
sufficient   = coverage >= target_months
```

---

### If I lost income today, how long could I sustain my lifestyle? 🔗

Extends the emergency fund question. If the fund earns a return while being drawn down:

```
months = periods_to_target(
    target_fv   = Decimal("0"),
    pmt         = avg_monthly_burn,
    annual_rate = fund_return,
    freq        = MONTHLY,
    initial_pv  = liquid_balance,
)
```

---

## 11. Debt strategy

### In what order should I pay off multiple debts? 📊 + sorting

Two strategies:

- **Avalanche** (minimises interest): sort debts by `annual_rate` descending, direct surplus to highest-rate debt first.
- **Snowball** (psychological wins): sort by `remaining_balance` ascending.

```
debts_avalanche = sorted(debts, key=lambda d: d.annual_rate, reverse=True)
debts_snowball  = sorted(debts, key=lambda d: d.remaining_balance)
```

For each ordering, compute total interest across all debts using `amortization_schedule`.

---

### At what rate does it stop making sense to hold savings instead of paying down debt? ✅

Above this threshold, the guaranteed after-tax saving from debt repayment beats the
expected investment return.

```
debt_rate       = annual_rate_on_debt
investment_rate = expected_return_on_savings

# If investment_rate_after_tax < debt_rate → repay debt first
crossover_reached = (investment_rate * (1 - marginal_tax_rate)) < debt_rate
```

---

## 12. Investment scenarios

### What is my portfolio's break-even inflation rate? 🔗

The inflation level that would completely erode my real return:

```
nominal_return     = xirr(cashflows, dates)
# Solve real_rate(nominal_return, inf) = 0 for inf:
# (1 + nominal) / (1 + inf) - 1 = 0  →  inf = nominal_return
breakeven_inflation = nominal_return
```

The nominal XIRR *is* the break-even inflation rate — real return is zero when
inflation equals the nominal return.

---

### How much would a 20% drawdown reduce my net worth, and how long to recover? 🔗

```
drawdown_loss  = portfolio_value * Decimal("0.20")
value_after    = portfolio_value - drawdown_loss

# Years to recover back to original value at assumed return
recovery_years = years_to_target(value_after, portfolio_value, assumed_return, ANNUAL)
```

---

### What lump sum today is equivalent to N years of monthly contributions? ✅

```
equivalent_lump_sum = pv_annuity(monthly_contribution, expected_return, years, MONTHLY)
```

---

## 13. Large purchases — lease vs buy

### Is it cheaper to lease or buy a car over N years? 🔗

**Buy scenario (net cost)**
```
# Finance the purchase
monthly_loan_pmt = payment(purchase_price - deposit, loan_rate, loan_years, MONTHLY)
total_loan_cost  = monthly_loan_pmt * (loan_years * 12) + deposit
# Recover resale value at end of N years
resale_pv        = present_value(resale_value, discount_rate, N, ANNUAL)
net_cost_buy     = total_loan_cost - resale_pv
```

**Lease scenario**
```
total_lease_cost = monthly_lease * (N * 12) + upfront_fee
# No residual value to recover
```

**Decision:** `net_cost_buy` vs `total_lease_cost` — lower number wins (after adjusting
for mileage limits, maintenance differences, etc.).

---

### Pay cash vs finance — which is better if the cash could be invested? 🔗

```
# Option A: pay cash — opportunity cost of not investing
opportunity_cost = future_value_compound(cash_price, investment_rate, N, ANNUAL) - cash_price

# Option B: finance — interest paid to lender
schedule         = amortization_schedule(cash_price, loan_rate, N, ANNUAL)
interest_cost    = sum(r.interest_payment for r in schedule)

# Pay cash if opportunity_cost < interest_cost (i.e. investment return < loan rate)
```

---

## 14. Children & dependants

### What will a monthly education savings plan be worth at age 18? 🔗

```
years_to_university = 18 - child_current_age

# Existing balance grows as lump sum
fv_existing      = future_value_compound(current_education_savings, return_rate, years_to_university, MONTHLY)

# New contributions grow as annuity
fv_contributions = fv_annuity(monthly_education_contribution, return_rate, years_to_university, MONTHLY)

projected = fv_existing + fv_contributions
```

---

### What lump sum do I need today to fund university costs in 18 years? 🔗

University costs inflate faster than general CPI — use a separate education inflation rate.

```
# Step 1: inflate today's university cost to arrival date
future_cost = future_value_compound(todays_annual_cost * years_at_uni, education_inflation, years_to_go, ANNUAL)

# Step 2: discount back to today at investment return
lump_sum_needed = present_value(future_cost, investment_return, years_to_go, ANNUAL)
```

---

## 15. Retirement — extended

### What is my "financial independence number"? 🔗

The portfolio size at which investment returns alone cover annual expenses (25× rule /
configurable safe withdrawal rate):

```
annual_expenses   = monthly_expenses * 12
swr               = Decimal("0.04")          # 4% safe withdrawal rate
fi_number         = annual_expenses / swr

# Equivalently, PV of a perpetuity:
# fi_number ≈ pv_annuity(monthly_expenses, swr, very_large_n, MONTHLY)
```

---

### How does delaying contributions by 5 years affect the retirement pot? 🔗

```
# Pot if starting today
pot_now   = fv_annuity(monthly_contribution, expected_return, years_to_retirement, MONTHLY)

# Pot if starting 5 years late
pot_late  = fv_annuity(monthly_contribution, expected_return, years_to_retirement - 5, MONTHLY)

cost_of_delay         = pot_now - pot_late
cost_in_todays_money  = present_value(cost_of_delay, inflation_rate, years_to_retirement, ANNUAL)
```

---

### How does retiring 2 years earlier change what I need to save? 🔗

Two effects compound: a larger nest egg is required (longer drawdown) *and* there are
fewer years to accumulate it.

```
# Nest egg needed if retiring 2 years earlier
nest_egg_early = pv_annuity(monthly_drawdown, return_in_retirement, life_expectancy - (target_age - 2), MONTHLY)

# Projected portfolio with 2 fewer accumulation years
projected_early = fv_annuity(monthly_contribution, expected_return, years_to_retirement - 2, MONTHLY) \
                + future_value_compound(current_savings, expected_return, years_to_retirement - 2, MONTHLY)

gap = nest_egg_early - projected_early
```

---

### What is my projected retirement income from my portfolio + state pension? 📊 + 🔗

```
# Monthly drawdown the nest egg can sustain
monthly_portfolio_income = payment(projected_nest_egg, return_in_retirement, drawdown_years, MONTHLY)

state_pension_monthly = configured_value   # from config/

total_monthly_income = monthly_portfolio_income + state_pension_monthly
```

---

## Gap Summary

The following functions are missing from the library.

| Function | Formula | Priority | Used in |
|----------|---------|----------|---------|
| `payoff_periods(principal, annual_rate, pmt, freq)` | $n = -\ln(1 - rP/PMT) / \ln(1+r)$ | **High** | Overpayment, consolidation, fixed vs variable, buy vs rent |
| `sinking_fund_payment(target_fv, annual_rate, years, freq)` | $PMT = FV \cdot r / [(1+r)^n - 1]$ | **High** | Savings planner — most common personal planning question |
| `gross_from_net(net, tax_schedule)` | jurisdiction-specific bracket table | **Medium** | Net salary target, raise impact |

Everything else can be answered by composing the existing public API.

---

## Function Usage Heatmap

Functions that appear in the most question chains, in order (updated for §§9–15):

| Rank | Function | Chains |
|------|----------|--------|
| 1 | `future_value_compound` | 9 |
| 2 | `fv_annuity` | 8 |
| 3 | `pv_annuity` | 7 |
| 4 | `amortization_schedule` | 7 |
| 5 | `present_value` | 6 |
| 6 | `payment` | 6 |
| 7 | `periods_to_target` | 4 |
| 8 | `xirr` | 3 |
| 9 | `real_rate` | 3 |
| 10 | `cagr` | 2 |
| 11 | `years_to_target` | 1 |
| 12 | `annuity_required_rate` | 1 |
| 13 | `future_value_simple` | 0 |
| 14 | `irr` | 0 (subsumed by `xirr`) |
| 15 | `effective_annual_rate` | 0 (rate normalisation, pre-processing) |
| 16 | `nominal_from_ear` | 0 (rate normalisation, pre-processing) |
| 17 | `required_rate` | 0 |

`future_value_simple`, `irr`, `effective_annual_rate`, `nominal_from_ear`, and
`required_rate` are correct and well-tested but do not appear directly in user-facing
question chains. They are either pre-processing steps (rate normalisation) or edge-case
tools. They should stay in the library for completeness but are low priority for
dashboard exposure.
