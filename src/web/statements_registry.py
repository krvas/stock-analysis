"""Single source of truth for statement page identity (``/statements/{t}/{slug}``)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from src.models.statement import StatementType
from src.web.settings import SettingsDecl


@dataclass(frozen=True)
class StatementPage:
    slug: StatementType
    title: str
    heading: str
    order: int
    settings: SettingsDecl
    # Statement pages have no sub-pages; the shared nav reads this attribute
    # on wizard and statement pages alike.
    subpages: tuple[()] = ()


_STATEMENT_DECL: Final = SettingsDecl(uses=("basis",))

STATEMENT_PAGES: Final[tuple[StatementPage, ...]] = (
    StatementPage("income", "Income", "Income Statement", 1, _STATEMENT_DECL),
    StatementPage("balance", "Balance", "Balance Sheet", 2, _STATEMENT_DECL),
    StatementPage("cashflow", "Cash Flow", "Cash Flow Statement", 3, _STATEMENT_DECL),
)


def get_statement_page(slug: str) -> StatementPage | None:
    return next((p for p in STATEMENT_PAGES if p.slug == slug), None)
