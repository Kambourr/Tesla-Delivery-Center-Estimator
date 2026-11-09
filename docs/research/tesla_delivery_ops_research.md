# Tesla delivery operations: research for the delivery-center estimator

Prepared 2026-11-08 (PT) for Jacob Kambour's Tesla Delivery-Center Estimator. **Public sources only, no Tesla internal data.** This file is research. It does not change the repo. Every number has a source URL and a date. "Accessed" means the page was read on 2026-11-08. Values marked **ASSUMPTION** are engineering estimates with no public source behind them.

Repo placeholders reviewed (main, 2026-11-08): `data/defaults/assumptions.yaml` (assumptions_version 2026.11.0), `src/dce/model/{demand,costs,types}.py`, `src/dce/geo/catchment.py` (M0 stub, 15-mile radius contract), `docs/OPEN_QUESTIONS.md` items 1–5.

---

## 1. Findings: how Tesla delivery works today

### 1.1 Location types (Tesla "Find Us" categories)
Tesla lists **stores/galleries**, **service centers** and **delivery centers** as separate categories. Most delivery points share an address with a store and often a service center. Few delivery centers stand alone.

| US count (Tesla Find Us lists) | Value | Source / date |
|---|---|---|
| Delivery centers (US list) | **135** (CA 31, FL 19, IL 9, WA 6 …; **Texas shows 0**) | Count of entries on https://www.tesla.com/findus/list/deliverycenters/United+States, read in browser 2026-11-08 |
| Stores and galleries | 321 (68 mall galleries or pop-ups) | Tesla Find Us store list as compiled by https://listitglobal.com/tesla-showrooms-service-centers-usa/ (checked 2026-11-08) |
| Service centers | 226 (189 share an address with a store) | same, 2026-11-08 |
| Distinct US addresses | 358 | same, 2026-11-08 |
| California | 69 stores, 50 service centers, 31 delivery centers | same, plus the Tesla delivery list |
| Global "Tesla locations" (stores + service, all countries) | 1,286 (Q2'24) → 1,306 → 1,359 → 1,390 → 1,454 → **1,498 (Q3'25)** | Tesla Q3 2025 Update, operational summary, https://www.sec.gov/Archives/edgar/data/1318605/000162828025045861/exhibit991.htm (2025-10-22). Tesla stopped reporting this line after Q3 2025. The Q3 2026 deck doesn't have it. |
| Global Mobile Service fleet | 1,933 (Q3'24) → **1,699 (Q3'25)** | same |

Texas isn't on the delivery list, and some stores also hand over cars. So 135 undercounts the physical points where cars are handed over. Use it as a lower bound on the denominator.

### 1.2 The delivery process (app-centric, mostly "touchless")
- **At a Tesla location:** "follow the signs to the check-in area. Sign any available agreements, complete final payment and accept delivery of your vehicle in the Tesla app. Unlock and access your Tesla vehicle using the Tesla app. Explore … with interactive videos." (https://www.tesla.com/support/taking-delivery, accessed 2026-11-08). Paperwork, financing and trade-in are done in the app ahead of time. Handover is short and mostly self-guided, an evolution of the 2020 "Express"/touchless delivery (https://www.electrive.com/2020/03/25/tesla-introduces-new-delivery-options-in-the-usa/, 2020-03-25).
- **Home delivery (Carrier Direct):** "available for customers … who live **more than 220 miles** from the nearest Tesla delivery location … performed by independent carriers for a fee." Tesla recommends pickup at a location for faster delivery (same Tesla support page, accessed 2026-11-08). So inside about 220 miles, essentially all deliveries go through a center. For the model, that makes 220 miles the outer limit of any catchment. Separately, Tesla's seasonal advisors may "conduct direct deliveries from Delivery Centers to client homes" in dense metros (seasonal posting, below).
- **Prep work at the hub:** the North San Jose hub planning documents describe on-site software updates, tire replacement and minor repairs before scheduled pickups, with appointments required (https://www.wtfwire.com/finance/tesla-bay-area-expansion-leases/, 2026-04-17, citing SiliconValley.com and the Colliers Q1 2026 report; also https://therealdeal.com/san-francisco/2026/04/17/tesla-signs-industrial-leases-in-san-jose-and-fremont/, 2026-04-17).

### 1.3 End-of-quarter surges
- Tesla's own seasonal hiring targets the quarter end: "Seasonal Tesla Advisor … collaborate … to achieve outstanding **end-of-quarter delivery results**," $18.17–$23.04/h (NYC posting, listed 2026-09-21, https://emploive.com/jobs/4494432/seasonal-tesla-advisor-delivery-tesla).
- Delivery centers are reported packed in the final weeks, e.g. Giga Texas delivered "hundreds" of vehicles on 2025-09-30 (https://www.teslarati.com/tesla-giga-texas-production-off-the-charts-deliveries-q3-ends/, 2025-09-30). About one-third of Q3 2022 deliveries fell in the last two weeks (https://www.fool.com/investing/2022/10/25/the-biggest-bombshell-in-tesla-earnings-report/, 2022-10-25).
- Inventory days of supply swing with the quarter: 10 → 15 → 27 → 15 → 11 days, Q3'25 to Q3'26 (Tesla Q3 2026 Update, below).

### 1.4 Typical roles (job postings)
| Role | What it does | Bay Area pay (posting) | Source / date |
|---|---|---|---|
| Tesla Advisor, Delivery | Loan and DMV documents, scheduling, handover, store fleet; CA requires a DMV salesperson license | $18.88–$28.32/h, Sunnyvale (750 E El Camino Real) | https://justjobs.com/career/17621620/Tesla-Advisor-Delivery-California-Sunnyvale (2026-08-15) |
| Seasonal Tesla Advisor | Prep vehicles and paperwork; quarter-end deliveries, including to homes | $18.17–$23.04/h, NYC | emploive link above (2026-09-21) |
| Vehicle Detailer | Wash and prep for delivery | $22.71–$26.52/h, Colma | https://www.justjobs.com/career/18218799/Vehicle-Detailer-California-Colma (accessed 2026-11-08) |
| Inventory Control Associate | Yard and inventory | $22.71–$36.00/h, Fremont | https://www.justjobs.com/career/18781348/Inventory-Control-Associate-California-Fremont (accessed 2026-11-08) |
| Delivery Operations Manager | Headcount planning, site throughput | n/a | https://simplify.jobs/p/918a8b52-3df8-4fc0-a577-4be36c61f2bf/Delivery-Operations-Manager (accessed 2026-11-08) |

Tesla doesn't publish headcount per delivery center. Its 10-K gives only the global total: **134,785 employees at 2025-12-31** (FY2025 10-K, https://www.sec.gov/Archives/edgar/data/1318605/000162828026003952/tsla-20251231.htm, filed 2026-01-28).

### 1.5 Footprint and throughput (public filings and news)
| Site | Size | Throughput / staff | Source / date |
|---|---|---|---|
| Colma, CA (1500 Collins Ave; closest delivery center to San Mateo) | 12,840 SF main building (showroom, lounge, delivery and prep) on a former dealership lot, 8 Superchargers | n/a | Town of Colma site plans via https://teslanorth.com/2020/08/29/tesla-service-center-colma-san-francisco/ (2020-08-29) |
| North San Jose hub, 2256 Junction Ave (new 2026, not yet on the Find Us list) | **107,700 SF**, about **920 vehicle** storage, 117 staff and visitor stalls | prep and delivery hub | wtfwire / The Real Deal (2026-04-17); City of San José CEQA notice https://www.sanjoseca.gov/Home/Components/News/News/7231/4699 |
| Port Coquitlam, BC (sales + service + delivery) | **60,000 SF** on about 7.5 acres, about 650 parking spots | **about 40 deliveries/day** at full operation; **about 80 jobs** (council approval 2023) | https://www.bcteslaguy.com/tesla-port-coquitlam/ (2025-08-25; checked 2026-10-31) |
| Trafford Park, Manchester UK (delivery hub) | 149,819 SF | "average of **45 car deliveries per day**" in scheduled slots (planning statement) | https://www.logisticsmatters.co.uk/news/tesla-gearing-up-distribution-sites-in-uk/ (2025-07-09) |

At about 300 operating days, 40–45/day works out to roughly **12,000–13,500 deliveries/yr for a regional hub**. A store-attached delivery center like Colma is far smaller in building area and depends on outdoor lot storage.

### 1.6 Bay Area locations near San Mateo (94402), straight-line from the ZCTA centroid
| Location | Type | Distance |
|---|---|---|
| Hillsdale Shopping Center, San Mateo 94403 | mall pop-up (no delivery) | 1.4 mi |
| Burlingame, 50 Edwards Ct 94010 | store + service, **not on the delivery list** | 3.3 mi |
| **Colma** 94014 | store + **delivery** | **12.2 mi** |
| Palo Alto, 4180 El Camino Real 94306 | store + service (not on the delivery list) | 13.9 mi |
| Fremont Factory 94538 | delivery | 20.6 mi |
| Sunnyvale 94087 | store + service + delivery | 20.7 mi |
| North San Jose hub 95131 | delivery hub (2026) | 25.9 mi |
| Dublin 94568 | delivery | 26.4 mi |
| Corte Madera 94925 | delivery | 28.8 mi |
| Los Gatos 95032 | delivery | 34.2 mi |
| Vallejo / Gilroy / Santa Rosa | delivery | 41 / 56 / 71 mi |

The delivery list was read 2026-11-08. Distances come from Census 2024 ZCTA Gazetteer internal points, https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_zcta_national.zip.

So San Mateo has no delivery point today. Buyers on the Peninsula go to Colma (north) or Sunnyvale and Fremont (south). That gap is what makes San Mateo a sensible demo candidate.

---

## 2. Data: Tesla quarterly deliveries (official IR / SEC 8-K)

| Quarter | Model 3/Y | Other models | Total | Source (release date) |
|---|---|---|---|---|
| Q2 2024 | 422,405 | 21,551 | 443,956 | Q2 2025 Update, https://www.sec.gov/Archives/edgar/data/1318605/000162828025035738/exhibit991.htm (2025-07-23) |
| Q3 2024 | 439,975 | 22,915 | 462,890 | same |
| Q4 2024 | 471,930 | 23,640 | 495,570 | https://ir.tesla.com/press-release/tesla-fourth-quarter-2024-production-deliveries-and-deployments (2025-01-02) |
| Q1 2025 | 323,800 | 12,881 | 336,681 | Q2 2025 Update (2025-07-23) |
| Q2 2025 | 373,728 | 10,394 | 384,122 | https://www.sec.gov/Archives/edgar/data/1318605/000162828025033842/exhibit99111.htm (2025-07-02) |
| Q3 2025 | 481,166 | 15,933 | 497,099 | Q3 2026 Update (below) |
| Q4 2025 | 406,585 | 11,642 | 418,227 | Q3 2026 Update |
| Q1 2026 | 341,893 | 16,130 | 358,023 | Q3 2026 Update |
| Q2 2026 | 467,762 | 12,364 | 480,126 | Q3 2026 Update |
| **Q3 2026** | **478,237** | **8,295** | **486,532** | https://www.sec.gov/Archives/edgar/data/1318605/000162828026064366/exhibit991111111.htm (2026-10-02); Q3 2026 Update 8-K Ex. 99.1 (2026-10-21), https://www.stocktitan.net/sec-filings/TSLA/8-k-tesla-inc-reports-material-event-d0581c0d340c.html |

- **Annual totals:** 2024 = 1,789,226 (Q4 2024 release). 2025 = **1,636,129** (sum of the four quarters). 2026 Q1–Q3 = 1,324,681.
- **3/Y share** of deliveries: 95.2% (2024), 97.1% (2025), **98.3% (Q3 2026)**. Model S/X were sunset in mid-2026 (Q3 2026 10-Q MD&A: "fewer Model S and Model X deliveries after the product sunset in mid-2026", https://www.sec.gov/Archives/edgar/data/1318605/000162828026066775/tsla-20260930.htm, filed 2026-10-22).
- **Global quarter mix, 2025:** Q1 20.6%, Q2 23.5%, Q3 30.4% (US tax-credit pull-forward), Q4 25.6%.

---

## 3. SEC filings: context for delivery operations

| Item | Value | Source / date |
|---|---|---|
| Headcount, worldwide | 134,785 (2025-12-31) | FY2025 10-K (filed 2026-01-28), link above |
| Retail, delivery and service location counts | **Not disclosed** in the 10-K or 10-Q; last IR figure 1,498 global "Tesla locations" (Q3'25) | see §1.1 |
| Volume outlook | No numeric guidance. "Focused on maximum capacity utilization"; deliveries depend on demand, supply chain and allocation to the owned fleet; "largest backlog for our passenger vehicles in four years"; battery supply is the limiting factor | Q3 2026 Update, 2026-10-21 |
| 10-Q delivery-ops language | "we must work constantly to similarly increase vehicle delivery capability so that it does not become a bottleneck … continue to increase and staff our delivery, servicing and charging infrastructure" | Q3 2026 10-Q (2026-10-22) |
| 2026 capex | "**in excess of $20 billion**", including growth in "our retail, service and charging footprint" (mostly AI compute and factories). Q3'26 capex $4.73B | Q3 2026 10-Q; Q3 2026 Update |
| SG&A | Q3'26 $2,015M vs $1,562M in Q3'25. Through 9 months, +$1.65B (+40%): $870M SBC (CEO award), **$357M employee and labor costs**, **$275M facilities and software** | Q3 2026 10-Q MD&A |
| US revenue share | Q3'26 US revenue $12,495M of $28,046M (44.6%, includes energy and services) | Q3 2026 10-Q, Note on geographic revenue |
| Analyst consensus (labeled) | Company-compiled consensus before Q3: Q3'26 461,974 (actual 486,532). **FY2026 1,767,255**, which after the Q3 actual implies about 442,600 for Q4'26 (+6% YoY). FY2025 actual 1,636,129 | https://teslanorth.com/2026/09/29/tesla-ir-q3-2026-delivery-consensus/ (2026-09-29), summarizing Tesla IR's posted consensus |
| Analyst view 2027 (labeled, single analyst) | Gene Munster sees about 15% growth in FY2027 | https://finance.yahoo.com/markets/stocks/articles/tesla-q3-deliveries-beat-street-144012325.html (Oct 2026) |

**Implication for the model:** volume growth of roughly **+5% to +10% a year** in 2026–27 is a reasonable "growth" scenario, and flat is a reasonable "base". Tesla gives no official number.

---

## 4. Data: US, California and Bay Area shares and per-center volumes

### 4.1 US and California
| Metric | Value | Source / date |
|---|---|---|
| Tesla US sales, 2024 | 633,762 (KBB est.) | Cox Q4 2025 EV report, https://www.coxautoinc.com/wp-content/uploads/2026/01/Q4-2025-Kelley-Blue-Book-EV-Sales-Report.pdf (Jan 2026) |
| Tesla US sales, 2025 | **589,160** (46.2% of US EVs) → **36.0% of global deliveries** | same |
| Tesla US, Q1–Q3 2026 | **386,194** (Q3 144,094; Q2 124,800); 52.9% of US EVs YTD → **29.2% of global** | Cox Q3 2026 report (est. as of 2026-10-12), https://www.coxautoinc.com/wp-content/uploads/2026/10/Q3-2026-Kelley-Blue-Book-EV-Sales-Report-updated-as-of-10-12-26.pdf; https://www.businessinsider.com/tesla-leads-us-ev-sales-surge-gas-prices-climb-q3-2026-10 |
| Tesla US, trailing 12 months to Q3'26 | about 524,200 (Q4'25 ≈ 589,160 − 451,160 = 138,000, plus 386,194) | derived from the Cox reports |
| US Tesla mix, Q3 2026 | Model Y 99,037 (69%), Model 3 40,346 (28%), Cybertruck 4,323 (3%), S + X < 400 | Cox Q3 2026; https://electronmotion.com/2026/10/17/us-ev-sales-q3-2026/ (2026-10-17) |
| CA Tesla new registrations, 2025 | 179,656 (CNCDA/Experian). **169,650** (CEC/DMV new ZEV sales) | https://www.cncda.org/wp-content/uploads/Cal-Covering-4Q-25.pdf; CEC "New_ZEV_Sales" xlsx (data as of 2026-09-30, updated 2026-10-13), https://www.energy.ca.gov/files/zev-and-infrastructure-stats-data |
| CA Tesla, Q1–Q3 2026 | 121,822 (CNCDA); **117,584** (CEC: Q1 32,382 / Q2 45,903 / Q3 39,299) | https://teslanewswire.com/articles/tesla-california-q3-2026-registrations-fall-15-percent-model-y-best-seller-cncda (2026-10-20); CEC xlsx |
| CA share of Tesla US | 28.8–30.5% (2025); about 30.4% (2026 YTD, CEC/Cox) | derived |
| Tesla share of CA ZEV registrations | 56.5% YTD 2026 (46.4% a year earlier) | CNCDA via teslanewswire (2026-10-20) |
| CA Tesla mix 2026 YTD (CEC) | Model Y 71.5%, Model 3 22.2%, Cybertruck 2.5%, X 2.4%, S 1.5% | CEC xlsx |

### 4.2 Bay Area counties (CEC new sales by county; the Tesla column is make = Tesla)
| County | Tesla 2024 | Tesla 2025 | Tesla 2026 Q1–Q3 | Tesla share of ZEV 2025 | BEV share of LDV stock (2025) | Tesla stock (2025) |
|---|---|---|---|---|---|---|
| San Mateo | 5,888 | **5,296** | 4,145 | 39% | 9.9% | 37,250 |
| San Francisco | 4,353 | 3,456 | 2,648 | 40% | 9.8% | 23,867 |
| Santa Clara | 19,565 | 20,214 | 14,218 | 55% | 11.7% | 115,429 |
| Alameda | 11,620 | 11,061 | 7,536 | 49% | 9.9% | 72,706 |
| Contra Costa | 7,251 | 5,535 | 4,074 | 41% | 7.5% | 42,137 |
| Marin | 1,703 | 1,259 | 1,015 | 27% | 9.8% | 10,265 |
| 9-county Bay Area | 54,232 | **49,704** | 35,728 | — | — | — |
| California | 201,167 | 169,650 | 117,584 | — | 5.9% | 1,076,112 |

Sources: CEC New ZEV Sales xlsx (data to 2026-09-30) and CEC Light-Duty Vehicle Population xlsx (data as of 2025-12-31, updated 2026-04-28), both from https://www.energy.ca.gov/files/zev-and-infrastructure-stats-data. The Bay Area is 29–30% of CA Tesla volume. San Mateo 2026 YTD mix: Model Y 72%, Model 3 21%, X 3.5%, S 2.4%, Cybertruck 1.6%.

### 4.3 Deliveries per center (calibration of `base_annual_deliveries`)
| Method | Calculation | Deliveries per center per year |
|---|---|---|
| US, 2025 | 589,160 ÷ 135 listed US delivery centers | **4,364** (an upper bound per point, since TX and store handovers aren't counted) |
| US, trailing 12 months to Q3'26 | 524,200 ÷ 135 | 3,883 |
| California, 2025 | 169,650 (CEC) ÷ 31 CA delivery centers | **5,473** |
| California, trailing 12 months | (117,584 + 39,563) ÷ 31 | 5,069 |
| Bay Area, nearest-center assignment (2025) | ZIP BEV sales × Bay Area Tesla/BEV ratio 0.528, each ZIP assigned to its nearest of 9 centers (within 40 mi) | range **1,450 (Santa Rosa) – 12,800 (Sunnyvale)**; Colma 9,600, Dublin 9,000, Fremont 6,600, Los Gatos 4,700, Vallejo 4,000, Corte Madera 3,500, Gilroy 2,100; mean about 6,000 |
| Regional hubs (planning docs) | 40–45/day × about 300 days | 12,000–13,500 |

### 4.4 San Mateo 94402 candidate: catchment demand (2025 CEC ZIP-level BEV sales × 0.528 Tesla ratio)
| Radius from 94402 | ZCTAs | BEV sales 2025 | Est. Tesla 2025 | Est. Tesla 2026 Q1–Q3 (ratio 0.616) |
|---|---|---|---|---|
| 5 mi | 8 | 4,854 | 2,563 | 1,863 |
| 10 mi | 21 | 8,660 | 4,572 | 3,382 |
| **15 mi** | 42 | 18,623 | **9,833** | 6,769 |
| 20 mi | 93 | 35,241 | 18,608 | 13,279 |
| 25 mi | 126 | 53,750 | 28,381 | 20,243 |

A 15-mile radius **double-counts** demand that Colma (12 mi) and Sunnyvale (21 mi) already serve. With existing centers taken into account:
- **Nearest-center (Voronoi) capture** for a new 94402 center: **about 4,370 Tesla deliveries/yr** (20 ZCTAs, mean 6.6 mi, p90 10.5 mi). Most of it comes out of Colma (9,600 → 7,000) and Sunnyvale (12,800 → 11,200).
- **Huff gravity capture** (equal attractiveness, distance exponent β): β=1.5 → 5,970; **β=2 → 5,720**; β=3 → 5,230 per year.

Script and outputs: `research/data/catchment_calc.py`, `radius_94402.csv`, `nearest_center_existing.csv`, `nearest_center_with_candidate_94402.csv`.

---

## 5. Proposed parameter values (low / base / high)

| assumptions.yaml key | Current | Low | **Base** | High | Basis |
|---|---|---|---|---|---|
| `demand.base_annual_deliveries` | 2,500 | 3,000 | **4,500** | 6,500 | US 4,364 per center (2025), CA 5,473 (2025), US trailing 12 months 3,883; San Mateo candidate 4,370 (Voronoi) to 5,720 (Huff). See §4.3–4.4 |
| `facility.catchment_miles` (fallback only) | 15 | 10 | **15** urban / 25 suburban | 35 | p90 distance to the nearest center: Colma 14 mi, Sunnyvale 13, Fremont 13, Los Gatos 16; exurban centers (Dublin, Vallejo, Gilroy, Santa Rosa) 35–37 mi. Hard outer limit 220 mi (Carrier Direct). Replace with the method in §6 |
| `facility.sqft` | 25,000 | 13,000 | **25,000** | 60,000 | Colma building 12,840 SF; Port Coquitlam 60,000 SF for about 40/day including service; dedicated hubs 108–150k SF for 12k+/yr. Optional scaling: **sqft = max(15,000, 5 SF × annual deliveries)** (ASSUMPTION, fit to Port Coquitlam). Yard storage of roughly 2 weeks of peak deliveries isn't in building SF; the San Jose hub stores about 920 vehicles |
| `labor.staffing.min_headcount` | 8 | 6 | **10** | 15 | ASSUMPTION: 7-day retail hours (Tesla postings require evenings and weekends): about 4 advisors, 3 prep/detail, 1 yard, 1 lead, 1 ops |
| `labor.staffing.deliveries_per_fte` | 250 | 200 | **300** | 450 | ASSUMPTION build-up: about 2.0 h advisor + 1.5 h prep/detail + 0.75 h yard per delivery, +15% supervision ≈ 4.9 h. At 1,800 productive h/FTE that's about 370 per FTE at average load, de-rated for a quarter-end peak about 2.5–3× average (partly covered by seasonal hires). Cross-check: Port Coquitlam about 80 jobs at about 12k deliveries/yr, including service staff, ≈ 150 per all-in FTE |
| `labor.wage_load` | 1.30 | 1.30 | **1.35** | 1.43 | BLS ECEC June 2026, private industry: total comp $46.89/h vs wages $32.82/h → 1.43 (https://www.bls.gov/news.release/ecec.nr0.htm). ECEC counts paid leave as a benefit while OEWS wages include it, so 1.35 is the base |
| Wage SOC mix (M2 loader; currently 49-3023) | 49-3023 | — | **41-2031 retail salespersons 45%, 53-7061 vehicle cleaners 30%, 53-7062/53-7065 yard and stock 15%, 41-1011 supervisors 10%** | — | The roles in §1.4. Auto service technicians (49-3023) are service-center staff, not delivery staff. Bay Area posting ranges are $18.88–$36.00/h |
| `Scenario.vehicle_mix` default | — | — | **Model Y 0.70, Model 3 0.27, Cybertruck 0.03, S/X 0.00** | — | Cox US Q3'26 (69/28/3); CEC CA 2026 YTD (71.5/22.2/2.5); S/X sunset mid-2026 (10-Q) |
| Quarterly seasonality (new) | — | — | **Q1 0.23, Q2 0.26, Q3 0.28, Q4 0.23** | — | CEC CA Tesla 2024–25 average (2024: 24.0/27.2/26.8/21.9%; 2025: 22.4/24.5/29.8/23.3%). 2025 Q3 is inflated by the tax-credit pull-forward |
| Within-quarter month split (new) | — | 0.30/0.33/0.37 | **0.25/0.30/0.45** | 0.20/0.25/0.55 | ASSUMPTION anchored on about one-third of a quarter in its last 2 weeks (Motley Fool 2022) and the seasonal-advisor postings. Peak-day ≈ 2.5–3× the average day (e.g. 4,500/yr → about 12/day average, about 35/day in the last 2 weeks of Q3) |
| Volume growth scenario (new, M4) | — | 0% | **+5%/yr** | +10%/yr | FY2026 consensus 1,767,255 (+8% vs 2025); Munster +15% for 2027; Tesla gives no guidance |
| `demand.factors.ev_share.reference` | 0.03 | — | **recalibrate** | — | CA BEV share of LDV stock is 5.9% and San Mateo's is 9.9% (CEC 2025). 0.03 sits between US and CA levels, so a San Mateo site would score high. Set references to the **median over existing delivery-center catchments** at build time |
| `demand.factors.*.reference` (population, income, commute) | round placeholders | — | **recalibrate as above** | — | so that score = 1 means a typical existing Tesla delivery catchment |
| `capex.fitout_psf`, `opex_load`, `property_tax` | 115 / 0.15 / … | — | keep | — | No public Tesla figures found. The property-tax/NNN overlap remains an open question for Jacob |

---

## 6. Recommended catchment method

Replace "everything within 15 miles of the ZIP" with **demand allocated among competing centers**. The steps below are deterministic and use public data only.

1. **Demand per ZCTA (Tesla new deliveries/yr)**
   - **California (best case):** CEC new-ZEV sales by ZIP, BEV only (quarterly, public xlsx), times Tesla's share of BEV in the county or region from the CEC county sheet (make-level). Use trailing 4 quarters.
   - **Other states:** state Tesla volume (Cox/KBB US Tesla × state share from AFDC/Experian state registrations, or state DMV data where it's published) allocated to ZCTAs by `households × (income/ref)^0.3 × (EV stock share/ref)^0.5`. That's the existing elasticity form, so `dce.model.demand` survives as the fallback allocator.
2. **Supply points:** existing Tesla delivery centers from the Find Us delivery list (135 US on 2026-11-08), snapshotted into the seed with an `as_of` date and staleness. Add store addresses flagged "possible handover", plus known 2026 hubs such as San Jose 95131.
3. **Distance:** drive time if an offline router is available; otherwise straight-line × 1.25 circuity. Cap at 60 mi (beyond that, assume Carrier Direct or a far center; Tesla's home-delivery threshold is 220 mi).
4. **Allocation:**
   - **Base: Huff gravity model.** Candidate share of ZCTA z is `P_cz = d_cz^-β / Σ_k d_kz^-β`, with **β = 2** (sensitivity 1.5–3) and equal attractiveness.
   - **Low case: nearest-center (Voronoi).**
   - Report both "deliveries handled" `Σ_z D_z·P_cz` and **"cannibalized from"** each existing center (`Σ_z D_z·(P⁰_kz − P_kz)`). For San Mateo the result is **about 4,400 (Voronoi) to 5,700 (Huff β=2) per year**, mostly taken from Colma and Sunnyvale.
5. **Map:** ZCTAs where `P_cz ≥ 0.5` form the core catchment polygon; shade the rest by `P_cz`. For San Mateo: about 20 ZCTAs, p90 about 10.5 mi.
6. **Contract change:** `catchment_features(geo, radius_miles)` becomes `catchment_features(geo, centers, demand, beta)`. `radius_miles` stays only as a fallback when no center list is available. `base_annual_deliveries` becomes a **calibration fallback** used only when ZIP-level EV data is missing.

---

## 7. Caveats
- **Deliveries ≠ registrations.** CEC and CNCDA count registrations by owner ZIP or county, not by the center that handed the car over. Fremont Factory and other hubs also deliver to out-of-area buyers. CEC (DMV) and CNCDA (Experian) totals differ by about 5%.
- **Cox/KBB US figures are estimates,** not Tesla-reported. Tesla does not break out US or state deliveries.
- **The Find Us lists are live pages.** Texas is missing from the delivery list and stores also hand over cars. The 135 / 226 / 321 counts are snapshots taken 2026-11-08. The store and service counts come from a third-party compilation of Tesla's lists; I counted only the delivery list myself.
- **No public per-center staffing or capex data exist.** Staffing, sqft scaling and the month split marked ASSUMPTION are engineering estimates for Jacob to tune.
- **Straight-line distances** from ZCTA internal points understate travel across the Bay (bridges). Use drive time for production.
- **2025 is distorted** by the federal EV credit ending 2025-09-30 (Q3 pull-forward). 2026 Bay Area volumes run about 4% below 2025 on an annualized basis, while Tesla's share of BEV rose from 0.53 to 0.62.
- **Job-post pay** comes from aggregator mirrors of Tesla postings. Verify against tesla.com/careers before seeding.

---

## DCF extension (added 2026-11-08)

Demand calibration (is the catchment too low?) is in [`demand_calibration.md`](demand_calibration.md), with code in `data/demand_calibration.py`.

The discounted-cash-flow design, the input table with sources, and the illustrative San Mateo NPV/IRR/payback are in [`dcf_design.md`](dcf_design.md), with code in `data/dcf_san_mateo.py`. The proximity-elasticity check is in `data/proximity_elasticity.py`.
