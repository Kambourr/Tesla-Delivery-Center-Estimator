# Demand calibration: is the 94402 catchment too low?

Prepared 2026-11-09 for Jacob Kambour. **Research only.** Nothing here changes `src/dce/` or `data/defaults/assumptions.yaml`. Public sources only, no Tesla internal data. Each number has a URL and the date the page was read. "Read 11-08" means the page was read for `tesla_delivery_ops_research.md` on 2026-11-08, and that figure is quoted from there. "Read 11-09" means it was read for this note. Numbers marked **ASSUMPTION** have no public source behind them.

Reproduce the model numbers with `python3 docs/research/data/demand_calibration.py` from the repo root. It runs offline, writes nothing, and uses the shipped `dce` loaders and model.

## TL;DR

1. **"Colma gets about 1,600 a year" is a misreading of the output.** 1,638 is the volume the San Mateo candidate **takes from** Colma (`catchment.gravity.taken_from`). Colma's own modeled volume is **7,938 a year** before the candidate and 6,300 after it under gravity. Under nearest-center it is 9,592 before and 7,038 after. The CLI does not print each center's total, which is how the confusion arose.
2. **The model's demand base matches public registrations.** The demo extract holds 49,026 Tesla deliveries a year. 47,522 of them fall in the 9-county Bay Area, which is **95.6% of the 49,704** Tesla registrations CEC counts there for 2025. The missing 4.4% are North Bay ZIPs more than 55 miles from 94402. They don't affect Colma or San Mateo. There is no quarterly-versus-annual bug. The 60-mile cap drops nothing: every ZIP has a center in range.
3. **Public benchmarks do not support "several times higher".** Implied deliveries per center are about 4,400–4,900 nationally (2025), 5,500–6,200 in California, and 5,000–5,500 in the Bay Area. Only one center (Colma) sits in SF plus San Mateo counties, which together registered **8,752** new Teslas in 2025. Colma at 7,900–9,600 is already near that ceiling. A 3× scale would put Colma at 22,000 a year, which is 2.5 times every new Tesla registered in SF and San Mateo combined.
4. **Recommendation, for Jacob to decide.** Anchor ZIP demand to CEC county Tesla totals instead of the uniform 0.528 Tesla/BEV share. Then apply a handover factor H for volume that registrations miss: **low 1.00 / base 1.10 / high 1.30**.

| Case | San Mateo, gravity (nearest) | Colma before → after (gravity) | Standalone NPV | IRR | Incremental NPV |
|---|---|---|---|---|---|
| Shipped today | 5,523 (4,370) | 7,938 → 6,300 | +$13.92M | 85.8% | −$2.62M |
| Low (county-anchored, H 1.00) | 5,318 (3,990) | 7,360 → 5,845 | +$13.14M | 82.3% | −$2.62M |
| **Base (H 1.10)** | **5,849 (4,389)** | **8,096 → 6,429** | **+$15.15M** | **91.3%** | **−$2.61M** |
| High (H 1.30) | 6,913 (5,187) | 9,568 → 7,598 | +$19.17M | 108.8% | −$2.59M |
| Stress (H 3.00), not plausible | 15,953 (11,971) | 22,079 → 17,534 | +$53.31M | 240.6% | −$2.36M |

NPV is at the 13.6% WACC from `dce.model.dcf` on the same path as `estimate()`. The 25,000 SF facility is held fixed, so the high and stress rows overstate NPV (see §4.3). The incremental lens barely moves, because it scales cost and benefit together (ADR-0005).

---

## 1. Benchmarks

### 1.1 Volumes

| Series | Value | Source (read date) |
|---|---|---|
| Tesla US sales 2025 (Cox/KBB estimate) | **589,160** (Q4 138,000); 2024 633,762 | https://www.coxautoinc.com/wp-content/uploads/2026/01/Q4-2025-Kelley-Blue-Book-EV-Sales-Report.pdf (read 11-09) |
| Tesla US 2026 Q1–Q3 (Cox/KBB) | **386,194**; Q3 144,094 | https://www.coxautoinc.com/wp-content/uploads/2026/10/Q3-2026-Kelley-Blue-Book-EV-Sales-Report-updated-as-of-10-13-26.pdf (read 11-09) |
| Tesla US trailing 4 quarters to Q3 2026 | 524,194 = 138,000 + 386,194 | derived from the two Cox rows |
| Tesla US 2025 (Motor Intelligence) | 580,147 (unverified: compiled by a Reddit user from MI's monthly data) | https://reddit.sentinel-team.org/posts/1q6mr4c/snapshots/2026-01-10T03%3A31%3A24.282367Z (read 11-09) |
| Tesla global deliveries 2025 | 1,636,129 | Tesla IR / SEC 8-K quarterly reports, sum in `tesla_delivery_ops_research.md` §2 (read 11-08) |
| CA Tesla new registrations 2025, CNCDA/Experian | **179,656** | https://cleantechnica.com/2026/02/21/tesla-sales-declined-11-4-in-california-in-2025/ (read 11-09); −11.4% matches CNCDA Q4 2025 via https://www.insurancejournal.com/news/west/2026/01/27/855684.htm (read 11-09) |
| CA Tesla new sales 2025, CEC/DMV | **169,650** | CEC New_ZEV_Sales xlsx, data to 2026-09-30, https://www.energy.ca.gov/files/zev-and-infrastructure-stats-data (read 11-08) |
| CA Tesla 2026 Q1–Q3, CNCDA | **121,822**; Q3 43,994 | https://driveteslacanada.ca/news/tesla-california-sales-q3-2026-model-y/ (read 11-09). Cross-check: the CNCDA release gives a 9.3% share of 1,315,522 ≈ 122.3k, https://www.cncda.org/news/california-new-car-dealers-association-releases-q3-2026-auto-outlook/ (read 11-09) |
| CA Tesla 2026 Q1–Q3, CEC | 117,584 (Q1 32,382, Q2 45,903, Q3 39,299) | CEC xlsx (read 11-08) |
| Tesla 2025, CEC by county | San Mateo **5,296**, San Francisco **3,456**, Santa Clara **20,214**, Alameda 11,061, Contra Costa 5,535, Marin 1,259; 9-county **49,704** of 94,131 BEV | CEC xlsx, `tesla_delivery_ops_research.md` §4.2 (read 11-08) |
| Tesla 2026 Q1–Q3, CEC by county | San Mateo 4,145, SF 2,648, Santa Clara 14,218 | same |

### 1.2 Delivery locations

| Count | Value | Source (read date) |
|---|---|---|
| US delivery centers, live Find Us list | **135** (CA 31; Texas shows 0) | https://www.tesla.com/findus/list/deliverycenters/United+States (read 11-08, browser count) |
| US delivery centers, seed on `feat/us-delivery-centers` | **120** `delivery` rows + 1 hub + 2 `possible_handover`; CA **29** + the San Jose hub | `data/seed/tesla_delivery_centers_us_2026-11-08.csv` on that branch. Built from the Wayback capture https://web.archive.org/web/20241214220441/https://www.tesla.com/findus/list/deliverycenters/United+States and All the Places run 2026-10-17 (DATA_SOURCES §10 on that branch, read 11-08) |
| Bay Area delivery centers used by the model | 9 (Colma, Sunnyvale, Fremont Factory, Dublin, Corte Madera, Los Gatos, Vallejo, Gilroy, Santa Rosa), plus the North San Jose hub, which is left out | `data/seed/tesla_delivery_centers_2026-11-08.csv` |
| Centers by county | San Mateo: Colma. San Francisco: **none**. Santa Clara: Sunnyvale, Los Gatos, Gilroy (plus the San Jose hub). Alameda: Fremont, Dublin | same |

### 1.3 Implied deliveries per center

| Scope | Calculation | Per center a year |
|---|---|---|
| US 2025 | 589,160 ÷ 135 / ÷ 120 | **4,364 / 4,910** |
| US trailing 4 quarters | 524,194 ÷ 135 / ÷ 120 | 3,883 / 4,368 |
| California 2025, CEC | 169,650 ÷ 31 / ÷ 29 | **5,473 / 5,850** |
| California 2025, CNCDA | 179,656 ÷ 31 / ÷ 29 | 5,795 / 6,195 |
| California 2026 run-rate, CNCDA | 121,822 × 4/3 ÷ 29 | 5,601 (crude annualization) |
| Bay Area 9-county 2025 | 49,704 ÷ 9 / ÷ 10 with the hub | **5,523 / 4,970** |
| SF + San Mateo + Santa Clara 2025 | 28,966 ÷ 4 centers (Colma, Sunnyvale, Los Gatos, Gilroy) / ÷ 5 with the hub | 7,242 / 5,793 |
| SF + San Mateo only | 8,752 registrations; Colma is the only center | **≤ about 8,750 for Colma** from home demand, plus whatever it draws from Santa Clara |
| Model output (shipped) | gravity, 9 centers | Colma 7,938; Sunnyvale 11,081; Fremont 8,963; Dublin 7,013; mean 5,448 |
| Throughput reference | Port Coquitlam BC plan, about 40 deliveries a day (from "data from similar facilities", not a city document); Trafford Park UK, 45 a day | https://driveteslacanada.ca/news/tesla-proposes-60000-square-foot-sales-service-and-delivery-center-for-port-coquitlam-bc/ (read 11-09); https://www.logisticsmatters.co.uk/news/tesla-gearing-up-distribution-sites-in-uk/ (read 11-08) |

The model's Colma volume works out to about 26 a day over 300 operating days. That sits below the 40–45 a day planned for regional hubs and above the average US center. No public source gives a measured handover count for any Bay Area center. The North San Jose CEQA notice describes uses (showroom, inventory, customer pickup) on 107,719 SF but gives no deliveries per day: https://pubt.io/view/A4539D0383CBC8AA39981A07A720F99C47155CD8 (read 11-09; the sanjoseca.gov original returned 403).

## 2. Gap diagnosis

Model figures come from `demand_calibration.py`.

| Hypothesis | Finding | Effect on San Mateo |
|---|---|---|
| **Output misread** | The ~1,600 figure is `taken_from` Colma (1,638), not Colma's total (7,938 gravity / 9,592 nearest before the candidate). | **Main cause of the concern** |
| Quarterly vs annual or partial-year bug | None. `bev_2025` is a full year: the 9-county subset sums to 95.6% of the CEC 2025 Tesla total after applying 0.528. A quarter-only file would show about 25%. | 0 |
| ZIP set (55 mi from 94402) | Drops about 2,180 Tesla a year of 9-county demand (Sonoma, Napa, northern Solano), all served by Santa Rosa or Vallejo. San Joaquin and Santa Cruz edge ZIPs are included. | about 0 for SM and Colma, but the extract is wrong for any non-Peninsula candidate |
| 60-mile cap | Every extract ZIP has at least one center in range (0 unserved). | 0 |
| Uniform Tesla/BEV share 0.528 | Overstates SF (×1.12 vs CEC), San Mateo (×1.10), Marin (×1.59) and Contra Costa. Understates Santa Clara (×0.87). Anchoring to county totals **lowers** San Mateo to 5,318. | −4% |
| CEC new-sales definition | CEC infers a new sale from a DMV registration with under 120 odometer miles and a model year within one year, assigned by **mailing address**. Registrations can take up to 3 weeks to process, so quarter-end deliveries can slip into the next snapshot, and recent quarters get revised. https://www.energy.ca.gov/data-reports/energy-almanac/zero-emission-vehicle-and-infrastructure-statistics/new-zev-sales (read 11-09) | small; the annual total is robust |
| Leases | CEC doesn't say whether a lease uses the lessee or lessor mailing address. If lessor, leased Teslas would be placed at Tesla Finance's address and drop out of the Bay Area ZIPs. CEC is only 5.6% below CNCDA statewide, which caps this effect. | up to about +6% (inside H) |
| Fleet / rental | CNCDA totals appear to include fleet (its release splits out "retail (excl. fleet)"). Bulk fleet cars usually don't go through a retail handover, so fleet pulls the other way. | slightly negative |
| Cybertruck | The CEC pages say "light-duty" and give no GVWR cut-off, so inclusion is unconfirmed. The research CEC mix shows Cybertruck at 2.5% of CA Tesla in 2026, so it is at least mostly counted. Cox puts Cybertruck at 3% of US Tesla. | ≤ +3% |
| Used / CPO handovers | Tesla's FY2025 10-K mentions higher "used vehicle sales volume" inside services and other revenue but gives no unit count: https://www.sec.gov/Archives/edgar/data/1318605/000162828026003952/tsla-20251231.htm (read 11-09). Used cars are handed over at the same centers, and CEC excludes them. | **ASSUMPTION +3–15%** |
| Colma serving SF and beyond | Yes, already modeled: SF has no center, and SF ZIPs go mostly to Colma (nearest for all of them). The cap on this is the 8,752 SF + SM registrations. | already in |
| 2026 vs 2025 | San Mateo 2026 run-rate 5,527 (+4%), SF +2%, Santa Clara −6%, CA −10% YoY (CNCDA). The Tesla share of BEV rose (0.53 → 0.62) while BEV totals fell. | about 0 to +4% for San Mateo |
| Equal-attractiveness Huff | Spreads every ZIP across all nine centers, which moves Colma from 9,592 (nearest) to 7,938. That is a modeling choice, not a data gap. A Huff with attractiveness by site size would move volume toward Fremont and the San Jose hub, not toward San Mateo. | n/a |

**Conclusion.** The demand base is consistent with public registrations to within about 5%. The perceived gap comes from reading `taken_from` as a center total, not from missing data. The defensible upward adjustments (registrations CEC misses, leases, used/CPO handovers) are on the order of +5–30%. They do not justify a multiple.

## 3. Recommended calibration (for Jacob to decide)

1. **County-anchor the Tesla share.** For each ZIP, `D_z = BEV_z × (CEC Tesla_county / Σ_{z∈county} BEV_z)`. Keep 0.528 only where a county has no CEC row in the extract. This is a mechanical correction backed by public county data. San Mateo moves 5,523 → 5,318.
2. **Apply a handover factor H to all ZIPs**, because registrations are not handovers:
   - **Low H = 1.00.** CEC registrations are the handovers.
   - **Base H = 1.10.** CNCDA/CEC gap 1.059 (179,656 / 169,650, read above), rounded up for a small used/CPO allowance (**ASSUMPTION** about +4%).
   - **High H = 1.30.** Adds a larger used/CPO share (**ASSUMPTION** about +15%) and the 2026 Tesla share uptick (+4% for San Mateo).
3. **Resulting volumes and NPV:** the table in the TL;DR. Base: San Mateo **5,849** gravity (4,389 nearest), Colma 8,096 → 6,429, standalone NPV **+$15.15M** (+$1.23M vs shipped), incremental −$2.61M (unchanged).
4. **Optionally switch the year** to trailing 4 quarters once the CEC Q4 2025 county split is pulled. That moves San Mateo by about ±4%.
5. **Report each center's total** before and after the candidate next to `taken_from` in the CLI, so the output can't be read as Colma = 1,600. That is a code change for a later PR.

## 4. Caveats

1. **Deliveries are not registrations.** Fremont Factory and the San Jose hub may hand over cars to buyers from outside their area, and buyers choose a pickup site in the app. No public per-center handover data exists.
2. **County lists are hand-made.** `county_of()` in the script assigns each ZCTA to its main county. A ZCTA that straddles a county line is counted once.
3. **Facility size is fixed in the DCF.** It stays at 25,000 SF whatever the volume. The research sizing rule `sqft = max(15,000, 5 × deliveries)` (`tesla_delivery_ops_research.md` §5, ASSUMPTION) would need 29k SF at base and 35k SF at high. That adds lease and capex, so read the high and stress NPVs as upper bounds.
4. **Cox, KBB and Motor Intelligence US figures are estimates.** Tesla does not report US or state deliveries. The CNCDA unit counts above come from secondary articles. The CNCDA releases themselves give shares.
5. **The national seed changes gravity slightly.** Moving `delivery_center_sites()` to the national seed changes 94402 gravity to 5,483.3 (Stockton, Seaside and Sacramento come into range; DATA_SOURCES §10 on `feat/us-delivery-centers`). That is a −0.7% effect, independent of this calibration.
