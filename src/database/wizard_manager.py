"""DuckDB manager for wizard adjustment preferences (wizard.sql)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd

from src.config import DEFAULT_WIZARD_DB_PATH, WIZARD_SCHEMA_SQL_PATH
from src.database import wizard_tables as wt
from src.database.manager import (
    STAGING_PREFIX,
    BaseDatabaseManager,
    UpsertResult,
    utc_now,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeleteResult:
    """Outcome of a bulk delete operation."""

    table: str
    rows_deleted: int


class WizardDatabaseManager(BaseDatabaseManager):
    """Connection and upserts for ``adjustment_preferences``."""

    default_schema_path: Path = WIZARD_SCHEMA_SQL_PATH

    def __init__(
        self,
        db_path: Path | str | None = None,
        *,
        read_only: bool = False,
        auto_connect: bool = True,
    ) -> None:
        super().__init__(
            Path(db_path or DEFAULT_WIZARD_DB_PATH),
            read_only=read_only,
            auto_connect=auto_connect,
        )

    def __enter__(self) -> WizardDatabaseManager:
        self.connect()
        return self

    def _ensure_schema(self) -> None:
        if wt.ADJUSTMENT_PREFERENCES not in self.list_tables():
            self.initialize_schema()

    def upsert_adjustment_preferences(self, df: pd.DataFrame) -> UpsertResult:
        """Upsert rows into ``adjustment_preferences``.

        Conflicts on ``(ticker, exchange, adjustment_type, base_concept)`` update
        the existing preference so stored rules track the latest user intent.
        """
        table = wt.ADJUSTMENT_PREFERENCES
        self._ensure_schema()
        if df.empty:
            logger.debug("Skipping empty upsert for %s", table)
            return UpsertResult(table=table, rows_written=0)

        if self.read_only:
            raise RuntimeError("Cannot upsert on a read-only connection.")

        prepared = self._prepare_adjustment_preferences(df)
        conflict_cols = wt.UNIQUE_KEYS[table]
        missing = [c for c in conflict_cols if c not in prepared.columns]
        if missing:
            raise ValueError(f"{table} upsert missing columns: {missing}")

        staging = f"{STAGING_PREFIX}{table}"
        sql = _build_adjustment_preferences_upsert_sql(table, staging, conflict_cols)
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

    def read_adjustment_preferences(
        self,
        ticker: str,
        exchange: str,
    ) -> pd.DataFrame:
        """Return all adjustment preferences for a ticker on an exchange."""
        if wt.ADJUSTMENT_PREFERENCES not in self.list_tables():
            return pd.DataFrame(columns=list(wt.TABLE_COLUMNS[wt.ADJUSTMENT_PREFERENCES]))
        return self.query(
            """
            SELECT *
            FROM adjustment_preferences
            WHERE ticker = ? AND exchange = ?
            ORDER BY adjustment_type, base_concept
            """,
            [ticker.upper(), exchange.upper()],
        )

    def delete_adjustment_preferences(
        self,
        keys: list[tuple[str, str, str, str]],
    ) -> DeleteResult:
        """Hard-delete rows matching ``(ticker, exchange, adjustment_type, base_concept)``.

        ``keys`` uses the same conflict key as ``upsert_adjustment_preferences``.
        Ticker/exchange are upper-cased to match the normalization applied on
        upsert, so a delete for a lowercase ticker still hits the stored row.
        A no-op (no error) for an empty ``keys`` list or for keys that don't
        match any existing row.
        """
        table = wt.ADJUSTMENT_PREFERENCES
        if not keys:
            logger.debug("Skipping empty delete for %s", table)
            return DeleteResult(table=table, rows_deleted=0)

        if self.read_only:
            raise RuntimeError("Cannot delete on a read-only connection.")

        self._ensure_schema()

        conditions = []
        params: list[str] = []
        for ticker, exchange, adjustment_type, base_concept in keys:
            conditions.append("(ticker = ? AND exchange = ? AND adjustment_type = ? AND base_concept = ?)")
            params.extend([str(ticker).upper(), str(exchange).upper(), adjustment_type, base_concept])

        sql = f"DELETE FROM {table} WHERE {' OR '.join(conditions)}"
        con = self.connection
        before = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        con.execute(sql, params)
        after = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        rows_deleted = before - after

        logger.info("Deleted %d rows from %s", rows_deleted, table)
        return DeleteResult(table=table, rows_deleted=rows_deleted)

    def _prepare_adjustment_preferences(self, df: pd.DataFrame) -> pd.DataFrame:
        table = wt.ADJUSTMENT_PREFERENCES
        allowed = set(wt.TABLE_COLUMNS[table])
        extra = set(df.columns) - allowed
        if extra:
            logger.warning("Dropping unknown columns for %s: %s", table, sorted(extra))

        cols = [c for c in wt.TABLE_COLUMNS[table] if c in df.columns]
        out = df[cols].copy()

        if "ticker" in out.columns:
            out["ticker"] = out["ticker"].astype(str).str.upper()
        if "exchange" in out.columns:
            out["exchange"] = out["exchange"].astype(str).str.upper()

        now = utc_now()
        if "updated_at" not in out.columns:
            out["updated_at"] = now
        else:
            out["updated_at"] = out["updated_at"].fillna(now)

        for col in wt.TABLE_COLUMNS[table]:
            if col not in out.columns:
                out[col] = pd.NA

        for col, default in wt.SCHEMA_DEFAULTS.get(table, {}).items():
            if col in out.columns:
                out[col] = out[col].fillna(default)

        out = self._resolve_adjustment_ids(out)
        return out[list(wt.TABLE_COLUMNS[table])]

    def next_adjustment_id(self) -> int:
        """Return the next sequential ``adjustment_id`` (0, 1, 2, …)."""
        table = wt.ADJUSTMENT_PREFERENCES
        if table not in self.list_tables():
            return 0
        row = self.query(
            f"""
            SELECT COALESCE(MAX(TRY_CAST(adjustment_id AS INTEGER)), -1) + 1 AS next_id
            FROM {table}
            """
        )
        return int(row.iloc[0]["next_id"])

    def _resolve_adjustment_ids(self, df: pd.DataFrame) -> pd.DataFrame:
        """Assign ``adjustment_id`` for new rows; reuse ids for unique-key matches.

        Incoming ``adjustment_id`` values are ignored so callers outside this
        package cannot control primary keys.
        """
        table = wt.ADJUSTMENT_PREFERENCES
        conflict_cols = list(wt.UNIQUE_KEYS[table])
        if df.empty:
            return df

        out = df.copy()
        if "adjustment_id" in out.columns:
            logger.debug("Ignoring caller-supplied adjustment_id for %s", table)
            out = out.drop(columns=["adjustment_id"])

        existing = self.query(
            f"SELECT adjustment_id, {', '.join(conflict_cols)} FROM {table}"
        )

        if existing.empty:
            out["adjustment_id"] = [str(i) for i in range(len(out))]
            return out

        merged = out.merge(existing, on=conflict_cols, how="left")
        needs_id = merged["adjustment_id"].isna()
        if needs_id.any():
            next_id = self.next_adjustment_id()
            merged.loc[needs_id, "adjustment_id"] = [
                str(value) for value in range(next_id, next_id + int(needs_id.sum()))
            ]

        out["adjustment_id"] = merged["adjustment_id"].astype(str)
        return out


def _build_adjustment_preferences_upsert_sql(
    table: str,
    staging: str,
    conflict_cols: tuple[str, ...],
) -> str:
    update_cols = [c for c in wt.TABLE_COLUMNS[table] if c not in conflict_cols]
    set_clause = ", ".join(f"{c} = excluded.{c}" for c in update_cols)
    conflict_target = ", ".join(conflict_cols)
    return f"""
        INSERT INTO {table} BY NAME
        SELECT * FROM {staging}
        ON CONFLICT ({conflict_target}) DO UPDATE SET {set_clause}
    """
