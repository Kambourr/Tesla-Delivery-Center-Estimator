# ADR-0005: DCF with two benefit views and a Tesla-WACC default

- Status: accepted
- Date: 2026-11-08

## Context

Jacob asked for the tool to "act as a discounted cash flow model for a new
delivery center, how long it will take to pay off". A delivery center sells
nothing itself. The car is sold online and the center does the handover, so
any cash inflow has to be attributed to it. `docs/research/dcf_design.md` §1
compares four ways to do that.

## Decision

`dce.model.dcf` is a pure 10-year DCF with end-of-year cash flows. Year 0
holds upfront capex and pre-opening labor. It reports NPV, IRR, simple and
discounted payback, and a yearly cash-flow table.

**Two benefit views, always shown together:**

1. **Standalone (headline).** Delivery-fee contribution:
   `deliveries × (destination fee − inbound freight)`. The fee is a public
   per-delivery price that Tesla charges for the delivery function, so it
   gives the site a real payback. Its weakness is that the fee is not
   incremental, because a nearby center would collect it anyway.
2. **Incremental to Tesla (check).** It has three parts:
   - `constraint_share ×` (the status-quo cost of serving the volume by
     expanding an existing center, plus an annuity on the expansion fit-out);
   - the overtime premium avoided on peak-month volume (California 1.5×,
     with the peak share taken from the seasonality table);
   - a proximity uplift of `uplift × deliveries × GP per vehicle`.

   This lens answers "should Tesla build it?". Its key input,
   `constraint_share`, is not publicly observable, so it ships as a
   low / base / high range (0.5 / 0.75 / 1.0).

If standalone NPV is above 0 but incremental NPV is below 0, the site pays
for itself as a delivery business but adds value for Tesla only if the
existing centers really are capacity-bound. That gap is the decision
question, so the UI shows both lenses. `gp_allocation` (full automotive
gross profit per delivery) is available only as a labeled upper bound. It
is never a decision metric. Regulatory credits are excluded.

**Discount rate.** The default is Tesla's WACC, **13.6%** (CAPM with beta
about 2.0, Rf 4.86%, ERP 4.41%; debt is under 1.1% of capital). The low case
is 9.7% (project beta 1.1) and the high case is 16.3% (published WACC).

**Cost side reuses the cost model.** Each year calls
`annualized_components` with escalated rent, wage, and utility rates and
that year's headcount. Capex leaves the annual `capex` component and becomes
explicit year-0 cash. The static `$/delivery` still shows capex
straight-line so the top-3 drivers stay comparable. Year 1 with no ramp
reconciles exactly to the static components minus `capex`.

**Tax.** Federal 21% and California 8.84%, with state tax deductible
federally (combined 27.98%). Federal takes 100% bonus depreciation in year 0
(OBBBA). California takes 39-year straight line on improvements and 7-year
on equipment, and writes off the remaining basis at lease end. Negative tax
is a cash benefit, on the assumption that Tesla's consolidated income
absorbs it.

**Terminal value.** None by default, because leasehold improvements revert
at lease end. A renewal perpetuity is an option.

## Consequences

- `EstimateResult` gains `dcf: DcfViews | None = None` (standalone and
  incremental). The field is additive, so existing callers are unaffected.
- `assumptions.yaml` schema 2 adds a `dcf:` block and low / base / high
  ranges. M4 builds DCF shocks and an NPV tornado from those ranges.
- Property tax is treated as inside the NNN `opex_load` by default
  (`property_tax.included_in_nnn: true`). That is how the research figures
  were built, and it avoids counting the tax twice.
- The San Mateo goldens reproduce the research table: standalone NPV about
  +$9.7M, payback about 1.7 years. The incremental lens was rebuilt from the
  formula in the research, because the research script is not in the repo.
  It lands at about −$2.65M against the published −$2.8M.
- Bay Area inbound freight is far below the flat national fee, so a Bay Area
  site looks unusually profitable on the standalone lens. The incremental
  lens is the guard against reading too much into that.
- Tax treatment, especially California non-conformity, needs confirmation
  from a tax advisor. The tax inputs are table values, not code.
