"""Reusable DuckDB manager for connections, schema init, and DataFrame upserts."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from src.config import DEFAULT_DB_PATH, SCHEMA_SQL_PATH
from src.database import tables as t

DEFAULT_SCHEMA_SQL_PATH = SCHEMA_SQL_PATH

logger = logging.getLogger(__name__)

STAGING_PREFIX = "_staging_"


@dataclass(frozen=True)
class UpsertResult:
    """Outcome of a bulk upsert operation."""

    table: str
    rows_written: int


class BaseDatabaseManager:
    """DuckDB connection lifecycle and generic SQL helpers."""

    default_schema_path: Path = DEFAULT_SCHEMA_SQL_PATH

    def __init__(
        self,
        db_path: Path | str,
        *,
        read_only: bool = False,
        auto_connect: bool = True,
    ) -> None:
        self.db_path = Path(db_path).resolve()
        self.read_only = read_only
        self._connection: duckdb.DuckDBPyConnection | None = None
        if auto_connect:
            self.connect()

    def connect(self) -> duckdb.DuckDBPyConnection:
        """Open (or reuse) the DuckDB connection."""
        if self._connection is not None:
            return self._connection

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        logger.debug("Connecting to DuckDB: %s (read_only=%s)", self.db_path, self.read_only)
        self._connection = duckdb.connect(str(self.db_path), read_only=self.read_only)
        return self._connection

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        """Return the active connection, opening one if needed."""
        if self._connection is None:
            return self.connect()
        return self._connection

    def close(self) -> None:
        """Close the DuckDB connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None
            logger.debug("Closed DuckDB connection: %s", self.db_path)

    def __enter__(self) -> BaseDatabaseManager:
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def initialize_schema(self, schema_path: Path | None = None) -> None:
        """Apply DDL from the manager's schema SQL file."""
        if self.read_only:
            raise RuntimeError("Cannot initialize schema on a read-only connection.")

        path = (schema_path or self.default_schema_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Schema file not found: {path}")

        sql = path.read_text(encoding="utf-8")
        logger.info("Applying schema from %s", path)
        self.connection.execute(sql)

    def list_tables(self) -> list[str]:
        """Return base table names in the main schema."""
        rows = self.connection.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'main' AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        ).fetchall()
        return [r[0] for r in rows]

    def execute(self, sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> None:
        """Run a SQL statement without returning rows."""
        if params:
            self.connection.execute(sql, params)
        else:
            self.connection.execute(sql)

    def query(self, sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> pd.DataFrame:
        """Run SQL and return a pandas DataFrame."""
        if params:
            return self.connection.execute(sql, params).df()
        return self.connection.execute(sql).df()


class DatabaseManager(BaseDatabaseManager):
    """Manage DuckDB connections and typed upserts for the core ingestion tables.

    Usage::

        with DatabaseManager() as db:
            db.initialize_schema()
            db.upsert_dataframe(t.COMPANIES, companies_df)
            db.upsert_dataframe(t.PRICES, prices_df)

    Upserts use ``INSERT OR REPLACE`` on primary keys to avoid duplicate rows.
    """

    default_schema_path: Path = SCHEMA_SQL_PATH

    def __init__(
        self,
        db_path: Path | str | None = None,
        *,
        read_only: bool = False,
        auto_connect: bool = True,
    ) -> None:
        super().__init__(
            Path(db_path or DEFAULT_DB_PATH),
            read_only=read_only,
            auto_connect=auto_connect,
        )

    def __enter__(self) -> DatabaseManager:
        self.connect()
        return self

    def table_row_count(self, table: str) -> int:
        """Return row count for a table."""
        if table not in t.ALL_TABLES:
            raise ValueError(f"Unknown table: {table}")
        return int(self.query(f"SELECT COUNT(*) AS n FROM {table}").iloc[0]["n"])

    # -------------------------------------------------------------------------
    # Company lookups
    # -------------------------------------------------------------------------

    def get_company_id(self, symbol: str, exchange: str) -> int | None:
        """Look up ``company_id`` by symbol and exchange."""
        df = self.query(
            """
            SELECT company_id
            FROM companies
            WHERE symbol = ? AND exchange = ?
            """,
            [symbol, exchange],
        )
        if df.empty:
            return None
        return int(df.iloc[0]["company_id"])

    def next_company_id(self) -> int:
        """Return the next available ``company_id``."""
        df = self.query("SELECT COALESCE(MAX(company_id), 0) + 1 AS next_id FROM companies")
        return int(df.iloc[0]["next_id"])

    def resolve_company_ids(self, df: pd.DataFrame) -> pd.DataFrame:
        """Ensure ``company_id`` is set for rows identified by symbol + exchange.

        Rows with an existing ``company_id`` are kept. Rows with symbol/exchange
        match existing companies. Remaining rows receive new sequential ids.
        """
        if df.empty:
            return df.copy()

        required = {"symbol", "exchange"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"DataFrame missing columns for company resolution: {missing}")

        out = df.copy()
        if "company_id" not in out.columns:
            out["company_id"] = pd.NA

        existing = self.query("SELECT company_id, symbol, exchange FROM companies")
        if not existing.empty:
            merged = out.merge(
                existing,
                on=["symbol", "exchange"],
                how="left",
                suffixes=("", "_existing"),
            )
            # Prefer explicit id, then lookup, then allocate later
            out["company_id"] = merged["company_id"].combine_first(merged["company_id_existing"])

        needs_id = out["company_id"].isna()
        if needs_id.any():
            next_id = self.next_company_id()
            out.loc[needs_id, "company_id"] = range(next_id, next_id + int(needs_id.sum()))

        out["company_id"] = out["company_id"].astype(int)
        return out

    # -------------------------------------------------------------------------
    # Upserts
    # -------------------------------------------------------------------------

    def upsert_dataframe(
        self,
        table: str,
        df: pd.DataFrame,
        *,
        add_timestamps: bool = True,
    ) -> UpsertResult:
        """Upsert rows into ``table`` by primary key.

        For ``companies``, missing ``company_id`` values are auto-resolved from
        ``symbol`` + ``exchange`` or assigned sequentially when no match exists.
        Uses ``ON CONFLICT (company_id)`` for ``companies`` (multiple unique
        constraints) and ``INSERT OR REPLACE`` for all other tables.

        Args:
            table: One of the core table names.
            df: DataFrame whose columns are a subset of the table schema.
            add_timestamps: When True, set ``ingested_at`` / ``updated_at`` if absent.

        Returns:
            UpsertResult with number of rows written.
        """
        if table not in t.ALL_TABLES:
            raise ValueError(f"Unknown table: {table}. Expected one of {t.ALL_TABLES}")

        if df.empty:
            logger.debug("Skipping empty upsert for %s", table)
            return UpsertResult(table=table, rows_written=0)

        if self.read_only:
            raise RuntimeError("Cannot upsert on a read-only connection.")

        prepared = df
        if table == t.COMPANIES:
            prepared = self._prepare_companies_for_upsert(prepared)
            add_timestamps = False

        prepared = self._prepare_dataframe(table, prepared, add_timestamps=add_timestamps)
        pk_cols = t.PRIMARY_KEYS[table]
        missing_pk = [c for c in pk_cols if c not in prepared.columns]
        if missing_pk:
            raise ValueError(f"{table} upsert missing primary key columns: {missing_pk}")

        staging = f"{STAGING_PREFIX}{table}"
        sql = _build_upsert_sql(table, staging)
        con = self.connection
        try:
            con.register(staging, prepared)
            con.execute(sql)
        finally:
            try:
                con.unregister(staging)
            except duckdb.CatalogException:
                pass

        logger.info("Upserted %d rows into %s", len(prepared), table)
        return UpsertResult(table=table, rows_written=len(prepared))

    def load_parquet(
        self,
        table: str,
        parquet_path: Path | str,
        *,
        add_timestamps: bool = True,
    ) -> UpsertResult:
        """Read a Parquet file and upsert into ``table``."""
        path = Path(parquet_path)
        if not path.exists():
            raise FileNotFoundError(f"Parquet file not found: {path}")
        df = pd.read_parquet(path)
        return self.upsert_dataframe(table, df, add_timestamps=add_timestamps)

    # -------------------------------------------------------------------------
    # Incremental helpers (watermarks live in pipeline code / parquet metadata)
    # -------------------------------------------------------------------------

    def max_trade_date(self, company_id: int) -> pd.Timestamp | None:
        """Latest price date stored for a company."""
        df = self.query(
            "SELECT MAX(trade_date) AS d FROM prices WHERE company_id = ?",
            [company_id],
        )
        val = df.iloc[0]["d"]
        if pd.isna(val):
            return None
        return pd.Timestamp(val)

    def max_period_end(
        self,
        table: str,
        company_id: int,
        *,
        period_type: str | None = None,
    ) -> pd.Timestamp | None:
        """Latest ``period_end_date`` for financial tables."""
        if table not in (
            t.FINANCIALS,
            t.BALANCE_SHEETS,
            t.CASH_FLOWS,
        ):
            raise ValueError(f"max_period_end not supported for table: {table}")

        sql = f"SELECT MAX(period_end_date) AS d FROM {table} WHERE company_id = ?"
        params: list[Any] = [company_id]
        if period_type is not None:
            sql += " AND period_type = ?"
            params.append(period_type)

        df = self.query(sql, params)
        val = df.iloc[0]["d"]
        if pd.isna(val):
            return None
        return pd.Timestamp(val)

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _prepare_dataframe(
        self,
        table: str,
        df: pd.DataFrame,
        *,
        add_timestamps: bool,
    ) -> pd.DataFrame:
        """Align DataFrame columns to table schema and fill timestamps."""
        allowed = set(t.TABLE_COLUMNS[table])
        extra = set(df.columns) - allowed
        if extra:
            logger.warning("Dropping unknown columns for %s: %s", table, sorted(extra))

        cols = [c for c in t.TABLE_COLUMNS[table] if c in df.columns]
        out = df[cols].copy()

        now = utc_now()
        if add_timestamps:
            if table == t.COMPANIES:
                if "updated_at" not in out.columns:
                    out["updated_at"] = now
            elif "ingested_at" in t.TABLE_COLUMNS[table] and "ingested_at" not in out.columns:
                out["ingested_at"] = now

        # Add any remaining allowed columns not in df as NA, then apply schema defaults.
        for col in t.TABLE_COLUMNS[table]:
            if col not in out.columns:
                out[col] = pd.NA

        for col, default in t.SCHEMA_DEFAULTS.get(table, {}).items():
            if col in out.columns:
                out[col] = out[col].fillna(default)

        return out[list(t.TABLE_COLUMNS[table])]

    def _prepare_companies_for_upsert(self, df: pd.DataFrame) -> pd.DataFrame:
        """Resolve company ids and company-specific timestamps before upsert."""
        prepared = self.resolve_company_ids(df)
        now = utc_now()
        if "created_at" not in prepared.columns:
            prepared["created_at"] = now
        prepared["updated_at"] = now
        return prepared


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _build_upsert_sql(table: str, staging: str) -> str:
    """Build upsert SQL, using an explicit conflict target when required by DuckDB."""
    pk_cols = t.PRIMARY_KEYS[table]
    if table == t.COMPANIES:
        # companies has PRIMARY KEY (company_id) and UNIQUE (symbol, exchange);
        # DuckDB requires an explicit ON CONFLICT target when multiple exist.
        # resolve_company_ids assigns company_id before upsert; conflict on company_id.
        update_cols = [c for c in t.TABLE_COLUMNS[table] if c not in pk_cols]
        set_clause = ", ".join(f"{c} = excluded.{c}" for c in update_cols)
        pk_target = ", ".join(pk_cols)
        return f"""
            INSERT INTO {table} BY NAME
            SELECT * FROM {staging}
            ON CONFLICT ({pk_target}) DO UPDATE SET {set_clause}
        """

    return f"""
        INSERT OR REPLACE INTO {table} BY NAME
        SELECT * FROM {staging}
    """
