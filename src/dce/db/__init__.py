"""SQLite connection and migrations.

Contract: open the user database, apply ``schema.sql`` idempotently, and
copy bundled seed rows on first launch. No network. M0 is a stub.
"""
