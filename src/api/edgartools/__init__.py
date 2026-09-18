"""SEC financial statements via edgartools (standalone, no DuckDB)."""

from src.api.edgartools.source import get_statement_views

__all__ = ["get_statement_views"]
