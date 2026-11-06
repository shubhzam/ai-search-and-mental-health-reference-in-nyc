"""PostgreSQL connectivity for the collector."""

import psycopg
from pydantic import PostgresDsn


def check_database(database_url: PostgresDsn) -> None:
    """Raise if PostgreSQL cannot answer a simple query."""
    with psycopg.connect(str(database_url), connect_timeout=5) as connection:
        if connection.execute("SELECT 1").fetchone() != (1,):
            raise RuntimeError("Unexpected PostgreSQL health check result")
