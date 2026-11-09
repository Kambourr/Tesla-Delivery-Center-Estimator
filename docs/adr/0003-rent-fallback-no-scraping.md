# ADR-0003: Automatic rent, no scraping

- Status: accepted
- Date: 2026-11-09

## Context

The only required input is a US ZIP. Rent has to resolve with no typed
field. Commercial listing sites forbid scraping, and paid CRE APIs are a
poor fit for an offline student app. Broker market reports do publish
metro industrial asking rents.

## Decision

Rent comes from a bundled seed of metro industrial asking rents, curated
by hand from public CBRE, Cushman & Wakefield, Colliers, and JLL reports,
each row cited. ZIP maps to CBSA with the HUD crosswalk. A frozen model
adjusts that metro rent with ACS income, density, and median home value,
calibrated offline on the GSA Lease Inventory.

Fallback, first hit wins:

1. Observed CBSA industrial seed, unadjusted. A residential ACS factor is not applied on top of a broker comp for that submarket.
2. County GSA observations. The ZIP ACS model adjusts this base only when the ZIP's own CBSA has no industrial seed.
3. State industrial median, when at least three CBSA seeds exist, then a national industrial row.
4. HUD SAFMR, then this ZCTA's ACS gross rent, then the county median, the CBSA median, the state median, and the national median of ACS gross rent. Those steps are low-confidence residential proxies.

No LoopNet, Crexi, CoStar, CompStak, Reonomy, ATTOM, or Cherre. An optional
advanced rent override may exist later. ZIP alone must still resolve.
`resolve_rent` reads SQLite only.

## Consequences

- `data/seed/` holds cited headlines, not PDFs. See `data/seed/README.md`.
- The cost model receives `rent_psf_month` as a number. It does not look
  rent up.
- Low-confidence proxy results have to be visible in the UI.
- A refresh script may update government sources. It may not scrape listings.
