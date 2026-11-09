# ADR-0004: Gravity catchment net of existing centers

- Status: accepted
- Date: 2026-11-08

## Context

The M0 contract built the catchment as every ZCTA within 15 miles of the
candidate ZIP. That counts demand that existing Tesla delivery centers
already serve. For San Mateo 94402, a 15-mile radius holds about 9,800
Tesla deliveries a year, but Colma (12 mi) and Sunnyvale (21 mi) already
take most of them. A nearest-center split gives about 4,400 a year for a new
San Mateo site. A Huff gravity split with distance exponent 2 gives about
5,700 (`docs/research/tesla_delivery_ops_research.md` §4.4, §6).

Delivery volume is the denominator of `$/delivery` and the driver of the DCF
benefit, so the double count matters more than any cost input.

## Decision

The catchment is a Huff gravity model over ZCTAs, net of existing Tesla
delivery centers:

- **Demand per ZCTA** is Tesla deliveries a year. In California it comes
  from CEC ZIP-level BEV sales × Tesla's share of BEV (trailing four
  quarters). Elsewhere the existing elasticity form in `dce.model.demand`
  allocates state Tesla volume to ZCTAs.
- **Supply points** are the existing US delivery centers from Tesla's public
  Find Us delivery list, snapshotted into the seed with an `as_of` date and a
  staleness flag. Known 2026 hubs not yet on the list (for example North San
  José 95131) may be added with a citation.
- **Distance** is straight-line between ZCTA internal points × 1.25
  circuity, capped at 60 miles. Drive time can replace it later.
- **Allocation.** The candidate's share of ZCTA *z* is
  `P_cz = d_cz^-β / Σ_k d_kz^-β` over the candidate and every existing center,
  with equal attractiveness and **β = 2** (sensitivity 1.5–3). Nearest-center
  (Voronoi) assignment is the low case.
- **Outputs:**
  - deliveries handled, `Σ_z D_z · P_cz`;
  - volume taken from each existing center *k*, `Σ_z D_z · (P⁰_kz − P_kz)`;
  - per-ZCTA shares for the map. The core polygon is `P_cz ≥ 0.5`, and the
    rest is shaded by `P_cz`.

Contract: `catchment_features(geo, centers, demand, beta) -> GeoDataFrame`
(see `docs/MODULE_CONTRACTS.md`). `facility.catchment_miles` stays only as a
fallback when no center list is available. `demand.base_annual_deliveries`
becomes a calibration fallback used only when ZIP-level EV data is missing.

The implementation lives in `src/dce/geo/` and `src/dce/data/ingest/`. It
is being built separately from the DCF work.

## Consequences

- The seed gains a delivery-center table (address, ZCTA, lat/lon, `as_of`,
  source URL). The Find Us list is a live page, so the snapshot needs a
  staleness TTL.
- Results report "taken from Colma: N/yr", which makes cannibalization
  visible. The incremental DCF lens (ADR-0005) reads it.
- Registrations by owner ZIP are not deliveries by handover center. Fremont
  and other hubs also serve out-of-area buyers. The docs must say so.
- Straight-line distance understates trips across the Bay. Drive time is a
  later refinement, not a v1 requirement.
- Home delivery (Carrier Direct, more than 220 miles from a center) and
  multi-site optimization are out of scope.
