# Finance Math Library

`munger_matics.finance` is the quantitative core of Munger-Matics. It is a library of pure
functions for time-value-of-money calculations, interest rate conversion, loan amortization,
cash flow analysis, and portfolio return measurement.

All planning and projection features in the dashboard consume these functions. They are
implementation-agnostic: they take numbers in and return numbers out, with no database calls,
no Streamlit imports, and no side effects.

---

## Design Principles

**Pure functions, no classes.** Every function is a standalone computation. Inputs go in,
a result comes out. No hidden state, no object lifecycle. This makes every function trivially
testable and composable.

**`decimal.Decimal` for all monetary values.** Floating-point arithmetic is never used for
money. All monetary inputs and outputs are `Decimal`. Rates are also `Decimal` on input/output.

**Float only for exponentiation, immediately quantized.** Python's `Decimal` does not support
fractional exponents. The precision strategy is: convert to `float` for the exponent computation,
then immediately convert back via `Decimal(str(result))` and `quantize()` before returning.
Intermediate rounding is avoided — only the final output is rounded. This assumption is
commented in `_common.py`.

**Two rounding precisions.** Monetary outputs round to the nearest cent (2 decimal places,
`ROUND_HALF_UP`). Rate outputs round to 6 decimal places (e.g. `0.051162` for 5.1162%),
giving enough precision for meaningful rate comparisons.

**Rates as decimal fractions.** Rates are always passed as fractions: `0.05` means 5%.
Never `5.0`. No runtime guard is applied (a threshold-based guard would produce false errors
for high-rate scenarios). The convention is enforced by docstrings.

**Compounding frequency as `CompoundingFreq`.** An `IntEnum` whose integer value is
the number of compounding periods per year. This prevents `"monthly"` vs `"MONTHLY"` string
bugs and makes the math readable: `rate / freq.value`.

---

## Module Structure

```
src/munger_matics/finance/
    __init__.py      # public API — imports and re-exports everything
    _common.py       # private utilities: CompoundingFreq, _quantize, _quantize_rate, _newton_solve
    compounding.py   # lump-sum TVM: FV, PV, required rate, time to target
    annuities.py     # regular payments: loans, savings streams, amortization
    rates.py         # rate conversion: EAR, nominal, real rate, CAGR
    cashflows.py     # irregular cash flows: NPV, IRR, XIRR
```

The dependency order is strict:

```
_common.py            ← no internal dependencies
    ↓
compounding.py        ← imports _common
annuities.py          ← imports _common
rates.py              ← imports _common
cashflows.py          ← imports _common
```

No module imports from another module at the same level. All public names are re-exported
through `__init__.py`.

---

## `CompoundingFreq`

```python
from munger_matics.finance import CompoundingFreq
```

An `IntEnum` representing the number of compounding or payment periods per year.

| Member | Value | Use |
|--------|-------|-----|
| `ANNUAL` | 1 | Annual savings, bonds, year-on-year comparisons |
| `SEMI_ANNUAL` | 2 | Bond coupon payments |
| `QUARTERLY` | 4 | Some structured products, PEL interest |
| `MONTHLY` | 12 | Mortgages, regular savings, most personal finance |
| `DAILY` | 365 | Livret A, overnight rates |

All functions that accept a `CompoundingFreq` default to `CompoundingFreq.ANNUAL`.

---

## Module: `compounding`

Lump-sum time-value-of-money functions. These answer questions about a single amount
growing or shrinking over time.

---

### `future_value_simple`

$$FV = PV \cdot (1 + r \cdot n)$$

```python
future_value_simple(pv: Decimal, rate: Decimal, periods: int) -> Decimal
```

Future value under simple (non-compounding) interest. Used for short-term instruments
and as a conceptual baseline. Less common in practice than compound interest.

| Argument | Type | Description |
|----------|------|-------------|
| `pv` | `Decimal` | Present value. Must be ≥ 0. |
| `rate` | `Decimal` | Periodic interest rate. Must be ≥ 0. |
| `periods` | `int` | Number of periods. |

**Returns:** Future value rounded to the nearest cent.

**Example:**
```python
# €1,000 at 5% simple interest for 3 years
future_value_simple(Decimal("1000"), Decimal("0.05"), 3)
# → Decimal("1150.00")
# Calculation: 1000 × (1 + 0.05 × 3) = 1000 × 1.15
```

---

### `future_value_compound`

$$FV = PV \cdot \left(1 + \frac{r}{m}\right)^{m \cdot t}$$

```python
future_value_compound(
    pv: Decimal,
    annual_rate: Decimal,
    years: int | float,
    freq: CompoundingFreq = CompoundingFreq.ANNUAL,
) -> Decimal
```

Future value under compound interest. The standard model for savings accounts,
investments, and debt.

| Argument | Type | Description |
|----------|------|-------------|
| `pv` | `Decimal` | Present value. Must be ≥ 0. |
| `annual_rate` | `Decimal` | Annual interest rate. Must be ≥ 0. |
| `years` | `int \| float` | Investment horizon. May be fractional. |
| `freq` | `CompoundingFreq` | Compounding periods per year. Default: `ANNUAL`. |

**Returns:** Future value rounded to the nearest cent.

**Example:**
```python
# €1,000 at 5% compounded monthly for 1 year
future_value_compound(Decimal("1000"), Decimal("0.05"), 1, CompoundingFreq.MONTHLY)
# → Decimal("1051.16")
# Calculation: 1000 × (1 + 0.05/12)^12 ≈ 1051.1619
```

**Dashboard use:** Projecting Livret A or PEA balance growth. First component of
"will I reach my savings target?" (combine with `fv_annuity` for regular contributions).

---

### `present_value`

$$PV = \frac{FV}{\left(1 + \frac{r}{m}\right)^{m \cdot t}}$$

```python
present_value(
    fv: Decimal,
    annual_rate: Decimal,
    years: int | float,
    freq: CompoundingFreq = CompoundingFreq.ANNUAL,
) -> Decimal
```

The exact inverse of `future_value_compound`. Discounts a future amount back to its
worth in today's money.

**Example:**
```python
# What is €500,000 in 30 years worth in today's euros at 2.5% inflation?
present_value(Decimal("500000"), Decimal("0.025"), 30, CompoundingFreq.ANNUAL)
# → Decimal("237984.87")
```

**Dashboard use:** Inflation-adjusting any projected future value to today's purchasing power.
Pass `inflation_rate` as the `annual_rate` argument.

---

### `required_rate`

$$r = m \cdot \left[\left(\frac{FV}{PV}\right)^{\frac{1}{m \cdot t}} - 1\right]$$

```python
required_rate(
    pv: Decimal,
    fv: Decimal,
    years: int | float,
    freq: CompoundingFreq = CompoundingFreq.ANNUAL,
) -> Decimal
```

Annual rate needed for a lump sum to grow from `pv` to `fv` in the given time.

**Example:**
```python
# What annual return do I need to turn €50K into €100K in 10 years?
required_rate(Decimal("50000"), Decimal("100000"), 10)
# → Decimal("0.071773")   (7.18%)
```

---

### `years_to_target`

$$t = \frac{\ln(FV / PV)}{m \cdot \ln(1 + r/m)}$$

```python
years_to_target(
    pv: Decimal,
    fv: Decimal,
    annual_rate: Decimal,
    freq: CompoundingFreq = CompoundingFreq.ANNUAL,
) -> float
```

Time in years for a lump sum to grow from `pv` to `fv` at a given rate.

**Example:**
```python
# How long until €10K doubles at 5% compounded monthly?
years_to_target(Decimal("10000"), Decimal("20000"), Decimal("0.05"), CompoundingFreq.MONTHLY)
# → 13.89  (years)
```

---

## Module: `annuities`

Functions for regular, equal periodic payments — either accumulating (savings) or
decumulating (loan repayment). Also contains the amortization schedule generator.

---

### `payment`

$$PMT = PV \cdot \frac{r(1+r)^n}{(1+r)^n - 1}$$

```python
payment(
    pv: Decimal,
    annual_rate: Decimal,
    years: int | float,
    freq: CompoundingFreq = CompoundingFreq.ANNUAL,
) -> Decimal
```

Periodic payment for a fixed-rate loan. Where $r$ = `annual_rate / freq` and
$n$ = `years × freq`.

**Example:**
```python
# Monthly payment on a €300,000 mortgage at 3.5% over 25 years
payment(Decimal("300000"), Decimal("0.035"), 25, CompoundingFreq.MONTHLY)
# → Decimal("1502.53")
```

**Dashboard use:** Mortgage affordability check. Combine with income data to compute
debt-to-income ratio.

---

### `pv_annuity`

$$PVA = PMT \cdot \frac{1 - (1+r)^{-n}}{r}$$

```python
pv_annuity(
    pmt: Decimal,
    annual_rate: Decimal,
    years: int | float,
    freq: CompoundingFreq = CompoundingFreq.ANNUAL,
) -> Decimal
```

Present value of an ordinary annuity — the lump sum needed today to sustain `pmt`
per period for `years` years.

**Example:**
```python
# How much do I need saved to withdraw €2,000/month for 25 years at 4%?
pv_annuity(Decimal("2000"), Decimal("0.04"), 25, CompoundingFreq.MONTHLY)
# → Decimal("379417.85")
```

**Dashboard use:** Retirement nest egg calculator. "How much do I need at retirement
to sustain my target monthly income?"

---

### `fv_annuity`

$$FVA = PMT \cdot \frac{(1+r)^n - 1}{r}$$

```python
fv_annuity(
    pmt: Decimal,
    annual_rate: Decimal,
    years: int | float,
    freq: CompoundingFreq = CompoundingFreq.ANNUAL,
) -> Decimal
```

Future value of an ordinary annuity — what a stream of regular equal contributions
will be worth at the end of `years`.

**Example:**
```python
# Saving €500/month at 6% for 30 years
fv_annuity(Decimal("500"), Decimal("0.06"), 30, CompoundingFreq.MONTHLY)
# → Decimal("502257.52")
```

**Dashboard use:** Savings projections. Second component of "will I reach my target?"
— combine with `future_value_compound(current_balance, ...)` for the lump-sum component.

```python
# Correct two-component projection (do not omit either term)
fv_existing      = future_value_compound(current_balance, rate, years, MONTHLY)
fv_contributions = fv_annuity(monthly_saving, rate, years, MONTHLY)
fv_total         = fv_existing + fv_contributions
```

---

### `periods_to_target`

$$n = \frac{\ln\!\left(\frac{target + PMT/r}{PV + PMT/r}\right)}{\ln(1+r)}$$

```python
periods_to_target(
    target_fv: Decimal,
    pmt: Decimal,
    annual_rate: Decimal,
    freq: CompoundingFreq = CompoundingFreq.ANNUAL,
    initial_pv: Decimal = Decimal("0"),
) -> int
```

Number of whole periods needed to reach a savings target, given an existing balance
and regular contributions. Returns a ceiling integer (the first period where the
target is met or exceeded).

**Example:**
```python
# €10K saved, adding €500/month at 5% — how many months until €50K?
periods_to_target(
    Decimal("50000"), Decimal("500"), Decimal("0.05"),
    CompoundingFreq.MONTHLY, Decimal("10000")
)
# → 61  (months)
```

**Dashboard use:** "When do I reach my goal?" Combine with `date.today()` and
`relativedelta(months=n)` to get a target date.

---

### `annuity_required_rate`

Solves $PV(1+r)^n + PMT \cdot \frac{(1+r)^n - 1}{r} = target$ numerically for
the nominal annual rate.

```python
annuity_required_rate(
    target_fv: Decimal,
    pmt: Decimal,
    years: int | float,
    freq: CompoundingFreq = CompoundingFreq.ANNUAL,
    initial_pv: Decimal = Decimal("0"),
    guess: Decimal = Decimal("0.05"),
    tolerance: Decimal = Decimal("0.000001"),
    max_iterations: int = 200,
) -> Decimal
```

What annual return must my savings earn to reach a target, given a fixed contribution
and horizon? No closed-form solution — uses Newton-Raphson via `_newton_solve`.

**Example:**
```python
# I have €10K, save €500/month, want €100K in 10 years — what return do I need?
annuity_required_rate(
    Decimal("100000"), Decimal("500"), 10,
    CompoundingFreq.MONTHLY, Decimal("10000")
)
# → Decimal("0.041234")   (4.12%)
```

---

### `amortization_schedule`

```python
amortization_schedule(
    principal: Decimal,
    annual_rate: Decimal,
    years: int | float,
    freq: CompoundingFreq = CompoundingFreq.ANNUAL,
) -> list[AmortizationRow]
```

Generates a period-by-period loan repayment schedule. Returns a `list[AmortizationRow]`
where each row is an immutable Pydantic model.

**`AmortizationRow` fields:**

| Field | Type | Description |
|-------|------|-------------|
| `period` | `int` | Payment number (1-indexed) |
| `payment` | `Decimal` | Total payment this period |
| `principal_payment` | `Decimal` | Portion reducing the balance |
| `interest_payment` | `Decimal` | Portion going to interest |
| `remaining_balance` | `Decimal` | Balance after this payment |

The final period is adjusted so the balance reaches exactly `Decimal("0.00")`,
handling cumulative rounding drift.

**Example:**
```python
schedule = amortization_schedule(Decimal("200000"), Decimal("0.06"), 30, CompoundingFreq.MONTHLY)
total_interest = sum(row.interest_payment for row in schedule)
# → Decimal("231676.38")
```

**For dashboard display**, convert to Polars:
```python
import polars as pl
df = pl.DataFrame([row.model_dump() for row in schedule])
```

**Dashboard use:** Most load-bearing function in the library — appears in 6 distinct
question chains: total interest cost, interest vs principal breakdown at any point,
overpayment analysis, loan consolidation comparison, fixed vs variable scenario,
and buy vs rent modelling.

---

## Module: `rates`

Functions for converting between rate representations and computing growth rates.

---

### `effective_annual_rate`

$$EAR = \left(1 + \frac{r_{nom}}{m}\right)^m - 1$$

```python
effective_annual_rate(
    nominal_rate: Decimal,
    freq: CompoundingFreq = CompoundingFreq.ANNUAL,
) -> Decimal
```

Converts a nominal (stated) annual rate to an effective annual rate. A 5% nominal
rate compounded monthly is actually 5.1162% EAR — converting to EAR puts all rates
on a common basis for comparison.

**Example:**
```python
effective_annual_rate(Decimal("0.05"), CompoundingFreq.MONTHLY)
# → Decimal("0.051162")
```

---

### `nominal_from_ear`

$$r_{nom} = m \cdot \left[(1 + EAR)^{1/m} - 1\right]$$

```python
nominal_from_ear(ear: Decimal, freq: CompoundingFreq = CompoundingFreq.ANNUAL) -> Decimal
```

Inverse of `effective_annual_rate`. Useful when a broker quotes an EAR and you need
the equivalent monthly rate to pass to `payment()` or `fv_annuity()`.

---

### `real_rate`

$$r_{real} = \frac{1 + r_{nom}}{1 + \pi} - 1$$

```python
real_rate(nominal_rate: Decimal, inflation_rate: Decimal) -> Decimal
```

Fisher equation. Converts a nominal return to its real (inflation-adjusted) equivalent.
A 7% nominal return with 2.5% inflation gives 4.39% real growth.

**Example:**
```python
real_rate(Decimal("0.07"), Decimal("0.025"))
# → Decimal("0.043902")
```

**Dashboard use:** "Is my portfolio keeping pace with inflation?" Take `xirr(...)` result,
pass to `real_rate(...)` with the average annual inflation over the period.

---

### `cagr`

$$CAGR = \left(\frac{FV}{PV}\right)^{1/t} - 1$$

```python
cagr(pv: Decimal, fv: Decimal, years: int | float) -> Decimal
```

Compound Annual Growth Rate — normalises any multi-year change in value to a single
comparable annual rate. Use when there are no irregular cash flows (a clean start
and end value). Use `xirr` instead when contributions were made at irregular intervals.

**Example:**
```python
# Portfolio went from €10K to €18K in 5 years
cagr(Decimal("10000"), Decimal("18000"), 5)
# → Decimal("0.124734")   (12.47%)
```

---

## Module: `cashflows`

Functions for irregular cash flow series — sequences of payments at arbitrary amounts
and (for XIRR) arbitrary dates.

---

### `npv`

$$NPV = \sum_{t=0}^{n} \frac{C_t}{(1+r)^t}$$

```python
npv(rate: Decimal, cashflows: Sequence[Decimal]) -> Decimal
```

Net Present Value of a series of equally-spaced cash flows. The first cash flow
(`t=0`) is not discounted. Use a negative value for an initial investment and positive
values for returns.

**Example:**
```python
# Invest €1,000 today, receive €300, €420, €680 over 3 years at 10%
npv(Decimal("0.10"), [Decimal("-1000"), Decimal("300"), Decimal("420"), Decimal("680")])
# → Decimal("130.73")
# Positive NPV: this investment creates value at a 10% hurdle rate.
```

**Dashboard use:** Evaluating invest-vs-overpay-mortgage decisions. Feed both options
as cash flow sequences and compare NPVs at your personal hurdle rate.

---

### `irr`

Finds the rate $r$ where $NPV(r, cashflows) = 0$ using Newton-Raphson.

```python
irr(
    cashflows: Sequence[Decimal],
    guess: Decimal = Decimal("0.10"),
    tolerance: Decimal = Decimal("0.000001"),
    max_iterations: int = 100,
) -> Decimal
```

Internal Rate of Return for equally-spaced cash flows. Requires at least one
sign change (at least one positive and one negative cash flow).

**Note:** For real investment data with irregular contribution dates, prefer `xirr`.

---

### `xirr`

$$\sum_{i} \frac{C_i}{(1 + XIRR)^{d_i / 365}} = 0$$

```python
xirr(
    cashflows: Sequence[Decimal],
    dates: Sequence[date],
    guess: Decimal = Decimal("0.10"),
    tolerance: Decimal = Decimal("0.000001"),
    max_iterations: int = 100,
) -> Decimal
```

Extended IRR for cash flows at *irregular dates*. Each cash flow is discounted by
its actual elapsed time from the first date, expressed as a year fraction
(days / 365). Uses Newton-Raphson internally.

This is the correct and only fair way to measure portfolio performance when
contributions are made at irregular intervals (which is always the case in practice).

**Example:**
```python
# Invest €10,000 on 1 Jan 2025, receive €11,000 on 1 Jan 2026
xirr(
    [Decimal("-10000"), Decimal("11000")],
    [date(2025, 1, 1), date(2026, 1, 1)],
)
# → Decimal("0.100000")   (10%)
```

**Example — real portfolio return:**
```python
# cashflows: each contribution is negative, current portfolio value is final positive
# dates: the actual date of each transaction
rate = xirr(cashflows, dates)
real = real_rate(rate, avg_inflation)
```

---

## Precision Model Summary

| Scenario | Strategy |
|----------|----------|
| Monetary output | `Decimal`, 2 decimal places, `ROUND_HALF_UP` |
| Rate output | `Decimal`, 6 decimal places, `ROUND_HALF_UP` |
| Exponentiation | Convert to `float`, compute, convert back via `Decimal(str(x))`, then `quantize()` |
| Intermediate steps | No rounding until the final return value |
| Final period of amortization | Balance forced to exactly `Decimal("0.00")` to eliminate drift |
| DataFrame columns | Use Polars `pl.Decimal(scale=2)` when loading schedules into Polars |

---

## Confirmed Gaps

Two functions are missing from the library. Both appear in multiple question chains
in the [Financial Questions Map](finance-questions.md).

### `payoff_periods` — high priority

$$n = \frac{-\ln\!\left(1 - \frac{r \cdot P}{PMT}\right)}{\ln(1+r)}$$

Given a principal, rate, and a (potentially larger-than-minimum) payment, how many
periods until the loan is paid off? Needed for overpayment analysis,
consolidation comparison, and fixed vs variable mortgage scenarios.

```python
# Planned signature
def payoff_periods(
    principal: Decimal,
    annual_rate: Decimal,
    pmt: Decimal,
    freq: CompoundingFreq = CompoundingFreq.MONTHLY,
) -> int: ...
```

### `sinking_fund_payment` — high priority

$$PMT = FV \cdot \frac{r}{(1+r)^n - 1}$$

How much must I save per period to accumulate a target future value? The savings-side
inverse of `fv_annuity`. Answers the most common personal planning question:
*"How much do I need to save each month?"*

```python
# Planned signature
def sinking_fund_payment(
    target_fv: Decimal,
    annual_rate: Decimal,
    years: int | float,
    freq: CompoundingFreq = CompoundingFreq.MONTHLY,
) -> Decimal: ...
```

---

## Testing

112 tests covering all 20 public functions, located in `tests/finance/`.

All tests follow this convention:
- Expected values derived from textbook formulas
- Arithmetic shown explicitly in comments so any future rounding change can be audited
- Round-trip tests (e.g. `pv → fv → pv`) state the accepted tolerance and explain why
- Input validation tests verify `ValueError` semantics for all guarded arguments
