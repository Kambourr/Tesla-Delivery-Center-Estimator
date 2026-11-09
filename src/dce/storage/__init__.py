"""SQLite repository.

Contract: this package is the only place that opens the database or writes
SQL. Callers in ``data``, ``geo``, and the orchestrator receive a connection
from :func:`dce.storage.connection.get_connection` and pass it back into
repository functions. ``model`` and ``scenarios`` must not import this package.

``schema.sql`` ships inside the package. M1 applies it idempotently.
"""
