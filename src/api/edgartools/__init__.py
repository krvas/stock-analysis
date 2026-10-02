"""SEC financial statements via edgartools (standalone, no DuckDB)."""

from src.api.edgartools.source import load_statement_set

__all__ = ["load_statement_set"]
