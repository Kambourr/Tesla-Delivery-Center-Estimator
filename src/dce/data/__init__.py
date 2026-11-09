"""Data services above storage: staleness, curated rent seed, rent resolution.

Network access belongs in ``dce.data.ingest`` (``fetch_*`` only). This
package reads what storage already holds and resolves the public inputs
``estimate`` needs. It does not fetch them.
"""
