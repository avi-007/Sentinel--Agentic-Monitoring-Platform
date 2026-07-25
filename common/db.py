"""Pooled Postgres access via psycopg3. No ORM — services issue explicit SQL
(see each service's db_writer.py), which keeps the write path legible against
db/init/001_schema.sql for anyone reviewing the project.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator, Optional, Sequence

import structlog
from psycopg import Connection
from psycopg_pool import ConnectionPool

log = structlog.get_logger(__name__)

_pool: Optional[ConnectionPool] = None


def init_pool(dsn: str, min_size: int = 1, max_size: int = 5, connect_retries: int = 30) -> ConnectionPool:
    """Creates the module-level pool, retrying while Postgres is still starting
    up (compose's `pg_isready` healthcheck usually covers this, but this is
    cheap defensive belt-and-suspenders for local `docker compose up` races).
    """
    global _pool
    last_err: Optional[Exception] = None
    for attempt in range(connect_retries):
        try:
            _pool = ConnectionPool(dsn, min_size=min_size, max_size=max_size, open=True)
            _pool.wait(timeout=10)
            log.info("db.pool_ready")
            return _pool
        except Exception as exc:  # noqa: BLE001 - broad: any connect failure should retry
            last_err = exc
            log.warning("db.pool_not_ready_yet", attempt=attempt, error=str(exc))
            time.sleep(2)
    raise RuntimeError(f"Could not connect to Postgres after {connect_retries} retries: {last_err}")


def get_pool() -> ConnectionPool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized — call init_pool() first")
    return _pool


@contextmanager
def get_conn() -> Iterator[Connection]:
    with get_pool().connection() as conn:
        yield conn


def execute(sql: str, params: Sequence[Any] | dict | None = None) -> None:
    with get_conn() as conn:
        conn.execute(sql, params)


def fetch_all(sql: str, params: Sequence[Any] | dict | None = None) -> list[dict]:
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_one(sql: str, params: Sequence[Any] | dict | None = None) -> Optional[dict]:
    rows = fetch_all(sql, params)
    return rows[0] if rows else None
