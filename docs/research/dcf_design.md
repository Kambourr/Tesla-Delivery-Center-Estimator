# DCF layer for the Delivery-Center Estimator: research and design

*Research estimate prepared 2026-11-08 (America/Los_Angeles). Uses public data only, no Tesla internal data. The repo was not modified. Each number below gives its source URL and access/publication date. Rows marked **ASSUMPTION** have no public source and are for Jacob to decide.*

Owner's ask [pt17u]: "act as a discounted cash flow model for a new delivery center, how long it will take to pay off as well as all the info we are currently doing."

---

## 1. Benefit side: what is the "cash inflow" of a delivery center?

A delivery center sells nothing on its own. The car is sold online, and the center does the hand-off, so any inflow has to be attributed to it. I evaluated four definitions:

| Rank | Definition | Formula per year | Public inputs | Verdict |
|---|---|---|---|---|
| **1 (default)** | **Standalone site P&L, "delivery-fee contribution"** | deliveries × (destination fee − inbound freight from factory) | Destination fee **$1,390** on Model 3/Y, order fee $250 (GetTesla citing Edmunds, 2026-08-06, https://gettesla.com/articles/what-teslas-destination-and-order-fees-actually-cover). Tesla describes the fee as covering "shipping your vehicle from the factory to your delivery location". Freight: Transportli open-trailer index for the week of 2026-11-02, <500 mi average $343/car at $1.01/mi (https://transportli.com/auto-transport/price-index/) | **Recommended default.** It is a public, per-delivery price that Tesla charges specifically for the delivery function, so it turns the center into a profit center with a real payback. It is transparent and scales with the existing demand and catchment model. Weakness: the fee is not *incremental*, because Colma would collect it anyway. |
| 2 (toggle) | **Incremental to Tesla, "avoided cost + uplift"** | constraint_share × (status-quo cost to serve the relieved deliveries at the existing centers, incl. an expansion capex annuity) + overtime premium avoided + uplift% × deliveries × GP/vehicle | Peninsula rents (Kidder Mathews Q3 2026), CA overtime 1.5× (Labor Code §510), GP/vehicle $7,233 (Tesla TTM, see §3) | The economically correct "should Tesla build it?" lens. Its key input, how capacity-constrained Colma and Sunnyvale actually are, is not observable publicly, so it ships as a **toggle** with `constraint_share` low 0.5 / base 0.75 / high 1.0. |
| 3 (component of 2) | **Incremental gross profit from proximity** | uplift% × deliveries × GP/vehicle | GP/vehicle $7,233; Bucklin, Siddarth & Silva-Risso (2008) share elasticity to dealer density ≈0.6 (https://doi.org/10.1509/jmkr.45.4.473); my CA county regression (`data/proximity_elasticity.py`): log-distance coefficient −0.037, SE 0.068, n=43, **not significant** | Base 1%, range 0–3%. Tesla orders online, so the dealer-density literature overstates the effect. Kept as part of lens 2, never on its own. |
| 4 (ceiling only) | **Full automotive GP allocated per delivery** | deliveries × $7,233 | Tesla 10-K/10-Q | **Do not use as a decision metric.** It credits the center with the whole car's margin, which is earned by the factory and sales. Shown only as an upper bound. |

**Recommendation.** Make `benefit_mode: standalone` the default and show `incremental` beside it in the UI. If standalone NPV is above 0 but incremental NPV is below 0, the site pays for itself as a delivery business but doesn't create value for Tesla unless the existing centers are genuinely capacity-bound. That gap is the real decision question. Keep `gp_allocation` behind an "upper bound" label.

Regulatory credits are excluded everywhere. FY2025 credits were $1,993M and are reported separately from automotive sales (10-K, filed 2026-01-28).

---

## 2. Key inputs (low / base / high)

| Input | Low | Base | High | Source (date) |
|---|---|---|---|---|
| Steady-state deliveries/yr (San Mateo 94402) | 3,000 | 4,400 | 5,700 | Nearest-center capture 4,370; Huff β=2 5,720 (research §4.4, CEC ZEV sales to 2026-09-30) |
| Ramp Y1/Y2/Y3 | 60/85/100% | 75/95/100% | 90/100/100% | **ASSUMPTION** |
| Volume growth from Y4 | 0% | 5% | 10% | Research §6 (Tesla 2026 YTD deliveries ±; Q3'26 Update 2026-10-21) |
| Capacity cap | — | 6,600 (1.5× steady) | — | **ASSUMPTION** |
| Destination fee | $1,250 (−10%, ASSUMPTION) | $1,390 | $1,640 (+ $250 order fee) | GetTesla/Edmunds, 2026-08-06 |
| Inbound freight per car | $75 | $150 (**ASSUMPTION**, about 30 mi from Fremont with a carrier minimum) | $343 | Transportli price index, week of 2026-11-02 |
| GP per vehicle (ex credits, ex leasing) | $5,992 (FY2025) | $7,233 (TTM Q4'25–Q3'26) | $7,347 (Q3'26) | 10-K FY2025; Q3'26 Update 2026-10-21 |
| Proximity uplift | 0% | 1% | 3% | Bucklin et al. 2008; own regression (above) |
| Capacity-constraint share | 0.5 | 0.75 | 1.0 | **ASSUMPTION** (no public capacity data) |
| Footprint | — | 25,000 sf | — | Research §5 (placeholder) |
| Rent, NNN $/sf/mo | $1.74 (S. SF) | $2.14 (San Mateo) | $2.95 (Menlo Park) | Kidder Mathews Peninsula Industrial Q3 2026, https://kidder.com/market-reports/peninsula-industrial-market-report/ |
| NNN opex load | — | 15% | — | Existing assumptions.yaml placeholder |
| Rent escalation | 3.0% | 3.5% | 4.0% | CBRE US Industrial year-end 2025: avg 3.36%, 3.50–3.53% for 10–100K sf |
| Blended wage $/h | $20.73 (−20%) | $25.91 | $31.09 (+20%) | Tesla postings, Nov 2026: Sunnyvale advisor $18.88–28.32, Colma detailer $22.71–26.52, Fremont inventory $22.71–36; supervisor at $35 = ASSUMPTION |
| Wage load | 1.30 | 1.35 | 1.43 | BLS ECEC Jun 2026: total comp $46.89 vs wages $32.82 (1.43 all private) |
| Wage inflation | 2.5% | 3.1% | 4.0% | BLS ECI private wages, 12 mo to Sep 2026 |
| Deliveries per FTE | 200 | 300 | 450 | Research §5 |
| Utilities | — | 375 MWh × $0.2875 + 150 kW × $20.50 × 12 ≈ $145k/yr, +3%/yr | — | PG&E B-10 rates effective 2026-03-01 (eqore summary); kWh/sf and kW = ASSUMPTION |
| Fit-out hard cost $/sf | $60 | $100 | $160 | RLB Q3 2026 QCR (SF industrial $160–255/sf *shell*); TI ranges terrapincg 2026 (warehouse $5–20, flex $25–50, retail/office to $480). Tacoma Tesla collision-center TI ≈ $3M (News Tribune) |
| Soft cost + contingency on fit-out | — | 20% | — | Industry 8–15% soft + 5–10% contingency (terrapincg 2026) |
| Equipment & IT | $500k | $780k | $1.2M | 30 L2 ports × $8k ($4.5–12k, Qmerit/nuwatt 2026) + 2 × 150 kW DCFC × $120k ($90–150k, verdek 2026) + $300k IT/lifts/signage/furniture (ASSUMPTION) |
| Pre-opening | — | 3 months of Y1 labor, expensed | — | **ASSUMPTION** |
| WACC | 9.7% | 13.6% | 16.3% | Rf 4.86% (UST 10y, 2026-11-06); ERP 4.41% (Damodaran implied, 2026-11-01). Base: Ke = 4.86 + 2.0 × 4.41 ≈ 13.7%; debt is <1.1% of capital. Beta 1.94 (GuruFocus 2026-11-08) / 2.03 (DeepViews) / 2.00 (Baratelli 2026-06-30). Low uses project beta 1.1. High = GuruFocus WACC 16.32%. Published range 11.9–16.3% |
| Tax | — | Fed 21% + CA 8.84% → combined 27.98% | — | IRC §11; CA FTB. Tesla FY2025 effective rate 27% (10-K) |
| Fed depreciation | — | 100% bonus, Y0, on QIP + equipment | — | OBBBA (P.L. 119-21): permanent 100% bonus for property acquired after 2025-01-19 |
| CA depreciation | — | Improvements 39-yr SL (remaining basis written off at lease end); equipment 7-yr SL | — | CA does not conform to bonus or 15-yr QIP. **Verify with a tax advisor** |
| Horizon | 7.7 yrs (Tesla avg remaining lease) | 10 yrs (lease term) | 15 yrs | 10-K FY2025: weighted remaining term 7.7 yrs, lease discount rate 5.0% |
| Terminal value | none | none | renewal perpetuity g=2% | Leasehold improvements revert at lease end; renewal is a toggle |

Book depreciation (for display only, not cash): leasehold improvements straight-line over the shorter of useful life or lease term; equipment 3–15 yrs; computer equipment 3–6 yrs (Tesla 10-K FY2025 accounting policies).

---

## 3. Tesla anchors used

- **FY2025** (10-K filed 2026-01-28):
  - automotive sales revenue $65,821M, cost $56,267M, GP $9,554M;
  - cash (non-lease) deliveries 1,594,512, so GP/vehicle ≈ $5,992 and ASP ≈ $41,280;
  - regulatory credits $1,993M, excluded.
- **TTM Q4'25–Q3'26** (Q3'26 Update, 2026-10-21): automotive sales revenue $72,323M, cost $59,926M, GP $12,397M, 1,713,991 cash deliveries → **$7,233/vehicle**.
- **Cost of automotive sales includes "shipping and logistic costs"** (10-K). Delivery-center opex therefore sits inside COGS/SG&A and isn't separately disclosed.
- **Capex:** 2026 guidance is "in excess of $20 billion", including the retail/service/charging footprint; Q3'26 capex $4,732M; FY2025 leasehold improvements gross $4,439M. No public dollar figure exists for any individual Tesla delivery hub.

---

## 4. Illustrative San Mateo base case (RESEARCH ESTIMATE)

Script: `research/data/dcf_san_mateo.py`. Outputs: `dcf_san_mateo_output.md` and `dcf_san_mateo_{standalone,incremental,gp_allocation}.csv`. Cash flows are end-of-year, and Y0 holds capex plus pre-opening. Taxes assume Tesla's consolidated taxable income absorbs the Y0 bonus deduction.

**Standalone (default) base:**
- Capex $3.78M (fit-out $3.0M + equipment $0.78M), plus $0.20M pre-opening.
- **NPV @13.6% = +$9.7M.**
- **IRR ≈ 66%.**
- **Simple payback 1.7 yrs; discounted payback 2.0 yrs.**
- Opex runs about $1.8–3.4M/yr and EBITDA about $2.3–4.3M/yr.
- Model cost per delivery (opex + straight-line capex) ≈ $590–660.

| Yr | Deliveries | Benefit $k | Opex $k | EBITDA $k | Capex $k | Tax $k | FCF $k |
|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 200 | −200 | 3,780 | −850 | −3,130 |
| 1 | 3,300 | 4,092 | 1,806 | 2,286 | 0 | 626 | 1,659 |
| 2 | 4,180 | 5,183 | 2,103 | 3,080 | 0 | 849 | 2,231 |
| 3 | 4,400 | 5,456 | 2,233 | 3,223 | 0 | 889 | 2,334 |
| 5 | 4,851 | 6,015 | 2,513 | 3,502 | 0 | 967 | 2,535 |
| 10 | 6,191 | 7,677 | 3,410 | 4,267 | 0 | 1,033 | 3,234 |

| Lens / case | NPV | IRR | Payback (simple / disc.) |
|---|---|---|---|
| Standalone base @13.6% | +$9.7M | 66% | 1.7 / 2.0 yr |
| Standalone @9.7% / @16.3% | +$12.2M / +$8.3M | 66% | 1.7 / 1.9–2.0 yr |
| Standalone + renewal TV (g=2%) | +$17.6M | — | — |
| **Incremental**, 75% constrained + 1% uplift | **−$2.8M** | <0 | never |
| Incremental, 100% constrained + 3% uplift | +$2.3M | 29% | 3.4 / 4.8 yr |
| Incremental, 50% constrained, 0% uplift | −$6.7M | n/a | never |
| GP allocation (ceiling, not a decision metric) | +$116M | — | 0.2 yr |

**Tornado, standalone NPV in $M (base +9.7), largest swing first:**

| Driver | Low input → NPV | High input → NPV | Swing |
|---|---|---|---|
| Deliveries | 3,000 → 4.2 | 5,700 → 13.9 | 9.7 |
| Fee per delivery | $1,250 → 7.2 | $1,640 → 14.1 | 6.9 |
| Inbound freight | $343 → 6.3 | $75 → 11.0 | 4.8 |
| Deliveries per FTE | 200 → 7.0 | 450 → 11.3 | 4.3 |
| WACC | 16.3% → 8.3 | 9.7% → 12.2 | 3.9 |
| Growth | 0% → 8.0 | 10% → 10.9 | 2.9 |
| Fit-out | $160 → 8.3 | $60 → 10.6 | 2.3 |
| Wage | ±20% → 8.6 | → 10.8 | 2.2 |
| Rent | $2.95 → 8.4 | $1.74 → 10.3 | 1.9 |

**How to read this.** Even the worst single-variable case keeps standalone NPV positive, because Bay Area inbound freight is far below the national flat $1,390 fee. The fee cross-subsidizes far-from-factory regions, so a Bay Area site looks unusually profitable on this lens. The incremental lens hinges almost entirely on `constraint_share`. A new center adds Tesla value only if Colma/Sunnyvale would otherwise need expansion or overtime.

---

## 5. Model structure and repo integration (proposed; repo not modified)

- **New pure module `src/dce/model/dcf.py`** (no I/O, no LLM, consistent with the purity rules in MODULE_CONTRACTS.md):
  - `DcfInputs` (frozen dataclass): `horizon_years, ramp: tuple[float,...], growth, capacity_cap, benefit_mode: Literal["standalone","incremental","gp_allocation"], fee_per_delivery, fee_escalation, inbound_freight, gp_per_vehicle, uplift, constraint_share, status_quo_rent_psf_month, fitout_psf, soft_contingency, equipment, preopen_months, rent_escalation, wage_inflation, utility_inflation, wacc, fed_rate, state_rate, fed_bonus, state_improvement_life, state_equipment_life, terminal: Literal["none","renewal"], terminal_g`.
  - `DcfYear` (frozen): `year, deliveries, headcount, benefit, lease, labor, utilities, property_tax, other_opex, opex, ebitda, capex, tax, fcf, discounted_fcf, cumulative_fcf`.
  - `DcfResult` (frozen): `years: tuple[DcfYear,...], npv, irr: float|None, simple_payback_years: float|None, discounted_payback_years: float|None, total_capex, terminal_value`.
  - `run_dcf(geo, demand, costs: CostInputs, dcf: DcfInputs, scenario: Scenario) -> DcfResult`. For each year it calls the existing `annualized_components`/`staffing_headcount` logic with escalated rent and wage, so the DCF reuses the cost model rather than duplicating it. Year-1 values must reconcile with today's `EstimateResult.components`. Capex leaves the annualized `capex` component and becomes explicit Y0 cash.
  - Helpers `npv(rate, cfs)`, `irr(cfs)` (bisection, returns None if there's no sign change), `payback(cfs, rate=0)`.
- **`EstimateResult`** gains `dcf: DcfResult | None = None`, an additive field with a default, so existing callers are unaffected.
- **`data/defaults/assumptions.yaml`**: new `dcf:` block holding the base values above, each with `source`/`as_of` comments. Bump `schema_version` and `assumptions_version`, and extend the strict parser in `dce.model` for the new keys.
- **`src/dce/scenarios`**:
  - `Scenario` gains optional `discount_rate_shock=0`, `growth_shock=0`, `benefit_mode=None`.
  - `expand_default_scenarios` adds WACC low/high and growth 0/10%.
  - New `dcf_tornado(base_inputs, ranges) -> list[(driver, npv_low, npv_high)]`.
  - `driver_rank_stability` (Spearman) can rank NPV drivers the same way it ranks cost drivers.
- **Outputs / UI**:
  - yearly cash-flow table (CSV);
  - NPV / IRR / payback KPIs per lens;
  - cumulative-FCF payback chart;
  - tornado chart;
  - the existing map and cost-per-delivery remain.
- **Tests**:
  - NPV of a known annuity;
  - IRR round-trip;
  - payback interpolation;
  - Y1 opex equals the existing `annualized_total_cost` excluding capex;
  - each `benefit_mode` is monotonic in deliveries.

---

## 6. Open decisions for Jacob

1. **Default benefit lens.** Standalone fee (recommended) vs incremental. Also whether to include the $250 order fee.
2. **Capacity constraint at Colma/Sunnyvale** (`constraint_share`). This single number decides the incremental verdict.
3. **Proximity uplift.** 0%, 1% or 3%. My regression says about 0.
4. **Discount rate.** Corporate Tesla WACC (13.6%, beta ≈ 2) or a lower project-specific rate (about 9.7%) for a low-risk leased logistics site.
5. **Horizon and terminal value.** A 10-year lease with no TV (base), Tesla's 7.7-year average, or renewal.
6. **Capex.** $100/sf hard fit-out, the charger count, the 25,000 sf footprint and the 1.5× capacity cap.
7. **Ramp and growth curve**, and whether growth follows the Tesla-wide forecast or catchment BEV growth.
8. **Tax.** Whether to model state depreciation at all, or simplify to a single 27.98% rate with federal bonus. CA treatment needs advisor confirmation.
9. **Freight.** Use a per-mile function of factory-to-site distance so the tool generalizes beyond the Bay Area, where freight savings vs Colma ≈ 0.

## 7. Caveats
- None of these numbers are Tesla internal data. The fee and freight lens is an accounting attribution, not Tesla's own transfer pricing.
- Delivery-center costs are not separately disclosed in Tesla filings.
- Rents are industrial NNN asking rents, and a retail-adjacent site could cost more.
- Labor productivity (deliveries/FTE) is a placeholder with large NPV leverage.
