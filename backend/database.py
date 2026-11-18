"""
Database layer for MediCloak.
Supports PostgreSQL (via psycopg2 with connection pooling) with an automatic,
transparent local SQLite fallback (medicloak.db) when PostgreSQL is not running.
"""

import os
import sys
import re
import json
import uuid
import sqlite3
import threading
from datetime import datetime, timezone
from contextlib import contextmanager
from urllib.parse import urlparse, unquote
from dotenv import load_dotenv, find_dotenv

# Load environment variables from .env file
load_dotenv(find_dotenv())

import psycopg2
from psycopg2 import pool, extras

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/medicloak",
)

# Parse DATABASE_URL into components for psycopg2
def _parse_dsn(url: str) -> dict:
    parsed = urlparse(url)
    dbname = parsed.path.lstrip("/").split("?")[0]
    params = {
        "user": unquote(parsed.username) if parsed.username else "postgres",
        "password": unquote(parsed.password) if parsed.password else "",
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "dbname": dbname or "medicloak",
    }
    if parsed.query:
        for part in parsed.query.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                params[k] = v
    return params


_pool: pool.SimpleConnectionPool | None = None
_use_sqlite: bool = False
_sqlite_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "medicloak.db")
_tls = threading.local()


def _get_sqlite_conn():
    if not hasattr(_tls, "conn") or _tls.conn is None:
        _tls.conn = sqlite3.connect(_sqlite_file, check_same_thread=False)
        _tls.conn.row_factory = sqlite3.Row
    return _tls.conn


def _adapt_sql(sql: str) -> str:
    """Translate PostgreSQL-specific SQL syntax to SQLite equivalents."""
    sql = re.sub(r"TRUNCATE\s+TABLE\s+(\w+)[^;]*;?", r"DELETE FROM \1;", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bILIKE\b", "LIKE", sql, flags=re.IGNORECASE)
    sql = re.sub(
        r"COUNT\(\*\)\s+FILTER\s*\(WHERE\s+phi_detected\s*=\s*(?:TRUE|true|1)\)",
        "COUNT(CASE WHEN phi_detected THEN 1 END)",
        sql,
        flags=re.IGNORECASE,
    )
    sql = re.sub(r"date_trunc\('hour',\s*timestamp\)", "strftime('%Y-%m-%d %H:00:00', timestamp)", sql, flags=re.IGNORECASE)
    sql = re.sub(r"NOW\(\)\s*-\s*INTERVAL\s*'24 hours'", "datetime('now', '-24 hours')", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bNOW\(\)", "datetime('now')", sql, flags=re.IGNORECASE)
    if "jsonb_array_elements_text" in sql:
        sql = re.sub(r"jsonb_array_elements_text\s*\(\s*phi_types\s*\)\s*as\s*elem", "json_each(phi_types) as elem", sql, flags=re.IGNORECASE)
        sql = re.sub(r"\belem\s+as\s+phi_type\b", "elem.value as phi_type", sql, flags=re.IGNORECASE)
        sql = re.sub(r"\bGROUP\s+BY\s+elem\b", "GROUP BY elem.value", sql, flags=re.IGNORECASE)
    sql = sql.replace("%s", "?")
    return sql


class SQLiteCursorWrapper:
    """Wraps sqlite3.Cursor to behave like a psycopg2 DictCursor."""

    def __init__(self, cursor):
        self._c = cursor

    def execute(self, sql: str, params=None):
        sql = _adapt_sql(sql)
        if params is not None:
            new_params = []
            for p in params:
                if isinstance(p, datetime):
                    new_params.append(p.isoformat())
                elif isinstance(p, (dict, list)):
                    new_params.append(json.dumps(p))
                elif isinstance(p, uuid.UUID):
                    new_params.append(str(p))
                else:
                    new_params.append(p)
            params = tuple(new_params)
            return self._c.execute(sql, params)
        return self._c.execute(sql)

    def fetchone(self):
        row = self._c.fetchone()
        if not row:
            return None
        d = dict(row)
        for key in ("hour", "timestamp", "created_at"):
            if key in d and isinstance(d[key], str):
                try:
                    d[key] = datetime.fromisoformat(d[key].replace("Z", "+00:00").replace(" ", "T"))
                except Exception:
                    pass
        return d

    def fetchall(self):
        rows = self._c.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            for key in ("hour", "timestamp", "created_at"):
                if key in d and isinstance(d[key], str):
                    try:
                        d[key] = datetime.fromisoformat(d[key].replace("Z", "+00:00").replace(" ", "T"))
                    except Exception:
                        pass
            result.append(d)
        return result

    def close(self):
        try:
            self._c.close()
        except Exception:
            pass

    @property
    def rowcount(self):
        return self._c.rowcount


def get_pool() -> pool.SimpleConnectionPool | None:
    global _pool, _use_sqlite
    if _use_sqlite:
        return None
    if _pool is None:
        try:
            _pool = pool.SimpleConnectionPool(minconn=2, maxconn=10, dsn=DATABASE_URL)
        except Exception:
            try:
                params = _parse_dsn(DATABASE_URL)
                _pool = pool.SimpleConnectionPool(minconn=2, maxconn=10, **params)
            except Exception as e:
                print(f"[MediCloak] PostgreSQL connection unavailable ({e}). Activating built-in SQLite engine: {_sqlite_file}")
                _use_sqlite = True
                return None
    return _pool


@contextmanager
def get_connection():
    """Get a connection, auto-return on exit."""
    p = get_pool()
    if _use_sqlite or p is None:
        conn = _get_sqlite_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    else:
        conn = p.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            p.putconn(conn)


@contextmanager
def get_cursor(cursor_factory=None):
    """Get a cursor with auto-commit/rollback."""
    with get_connection() as conn:
        if _use_sqlite:
            cur = SQLiteCursorWrapper(conn.cursor())
            try:
                yield cur
            finally:
                cur.close()
        else:
            kwargs = {}
            if cursor_factory:
                kwargs["cursor_factory"] = cursor_factory
            cur = conn.cursor(**kwargs)
            try:
                yield cur
            finally:
                cur.close()


def dict_cursor():
    """Return RealDictCursor factory for dict-like rows."""
    if _use_sqlite:
        return None
    return extras.RealDictCursor


def init_db():
    """Create the events and vapi_calls tables if they don't exist."""
    get_pool()  # Probes PostgreSQL, sets _use_sqlite if unavailable

    if _use_sqlite:
        conn = _get_sqlite_conn()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id        TEXT DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-a' || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
                timestamp       TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                source_ip       TEXT,
                user_agent      TEXT,
                ai_service      TEXT,
                request_method  TEXT,
                request_path    TEXT,
                risk_score      INTEGER,
                severity        TEXT,
                phi_detected    INTEGER DEFAULT 0,
                phi_count       INTEGER DEFAULT 0,
                phi_types       TEXT DEFAULT '[]',
                phi_findings    TEXT DEFAULT '[]',
                original_text   TEXT,
                redacted_text   TEXT,
                action          TEXT,
                status          TEXT DEFAULT 'active',
                engine          TEXT,
                response_time_ms INTEGER,
                department      TEXT DEFAULT 'OPD / General Medicine',
                sha256_hash     TEXT,
                rehydration_map TEXT DEFAULT '{}',
                clinical_terms_preserved TEXT DEFAULT '[]',
                dpdp_score      REAL DEFAULT 99.8,
                created_at      TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS vapi_calls (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                call_id         TEXT,
                event_id        TEXT NOT NULL,
                source_ip       TEXT,
                phone_number    TEXT,
                status          TEXT DEFAULT 'initiated',
                created_at      TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                ended_at        TEXT,
                duration_seconds INTEGER,
                error_message   TEXT
            );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_event_id ON events(event_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp DESC);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_severity ON events(severity);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_department ON events(department);")
        conn.commit()
        print(f"[MediCloak] SQLite database initialized successfully at {_sqlite_file}")
        return

    # Native PostgreSQL initialization
    with get_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id              SERIAL PRIMARY KEY,
                event_id        UUID DEFAULT gen_random_uuid(),
                timestamp       TIMESTAMPTZ DEFAULT NOW(),
                source_ip       TEXT,
                user_agent      TEXT,
                ai_service      TEXT,
                request_method  TEXT,
                request_path    TEXT,
                risk_score      INTEGER,
                severity        TEXT,
                phi_detected    BOOLEAN DEFAULT FALSE,
                phi_count       INTEGER DEFAULT 0,
                phi_types       JSONB,
                phi_findings    JSONB,
                original_text   TEXT,
                redacted_text   TEXT,
                action          TEXT,
                status          TEXT DEFAULT 'active',
                engine          TEXT,
                response_time_ms INTEGER,
                department      TEXT DEFAULT 'OPD / General Medicine',
                sha256_hash     TEXT,
                rehydration_map JSONB DEFAULT '{}'::jsonb,
                clinical_terms_preserved JSONB DEFAULT '[]'::jsonb,
                dpdp_score      FLOAT DEFAULT 99.8,
                created_at      TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        # Auto-migration for existing tables
        cur.execute("""
            ALTER TABLE events ADD COLUMN IF NOT EXISTS department TEXT DEFAULT 'OPD / General Medicine';
            ALTER TABLE events ADD COLUMN IF NOT EXISTS sha256_hash TEXT;
            ALTER TABLE events ADD COLUMN IF NOT EXISTS rehydration_map JSONB DEFAULT '{}'::jsonb;
            ALTER TABLE events ADD COLUMN IF NOT EXISTS clinical_terms_preserved JSONB DEFAULT '[]'::jsonb;
            ALTER TABLE events ADD COLUMN IF NOT EXISTS dpdp_score FLOAT DEFAULT 99.8;
        """)

        # Create indexes
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_event_id ON events(event_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp DESC);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_severity ON events(severity);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_department ON events(department);")

        # VAPI voice calls table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS vapi_calls (
                id              SERIAL PRIMARY KEY,
                call_id         TEXT,
                event_id        UUID NOT NULL,
                source_ip       TEXT,
                phone_number    TEXT,
                status          TEXT DEFAULT 'initiated',
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                ended_at        TIMESTAMPTZ,
                duration_seconds INTEGER,
                error_message   TEXT
            );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_vapi_calls_event_id ON vapi_calls(event_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_vapi_calls_source_ip_created ON vapi_calls(source_ip, created_at DESC);")


def close_pool():
    """Close all connections."""
    global _pool, _use_sqlite
    if _pool:
        _pool.closeall()
        _pool = None
    if _use_sqlite:
        if hasattr(_tls, "conn") and _tls.conn:
            try:
                _tls.conn.close()
            except Exception:
                pass
            _tls.conn = None
