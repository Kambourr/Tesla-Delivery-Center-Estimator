# Delivery-center build fixtures

Small excerpts of the public inputs that `scripts/build_us_delivery_centers.py`
reads. The tests use them so the build logic runs with no network. Sources and
access dates are in `docs/DATA_SOURCES.md` section 10.

- `findus_list_sample.html`: eight entries (California, North Carolina,
  Texas) cut verbatim from the Wayback Machine capture
  `20241214220441` of Tesla's public Find Us US delivery-center list. Markup
  is unchanged. Monterey keeps its doubled house number and repeated city
  line. Long Beach keeps its all-caps address.
- `atp_tesla_sample.geojson`: seven US features from All the Places run
  `2026-10-17-13-32-31`, spider `tesla` (CC0). Two are the delivery-named
  sites that become `possible_handover` rows (Manhasset NY, Plano TX).
- `census_batch_sample.csv`: the U.S. Census Bureau batch geocoder answers
  for the eight entries above (benchmark `Public_AR_Current`, public domain),
  renumbered 0 to 7. Austin is `No_Match`.
- `overpass_sample.json`: two OpenStreetMap Tesla shops from Overpass (ODbL),
  Bakersfield and Fresno, with only the address, name, brand, and shop tags.
- `bay_area_sample.csv`: two rows (Colma and the North San Jose hub) copied
  from `data/seed/tesla_delivery_centers_2026-11-08.csv`.
