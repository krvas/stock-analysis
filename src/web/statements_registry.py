from __future__ import annotations

from typing import Final

from src.web.page_types import StatementPage
from src.web.settings import SettingsDecl
from src.web.settings_registry import SubpageSetting

_STATEMENT_DECL: Final = SettingsDecl(uses=(SubpageSetting.BASIS,))

STATEMENT_PAGES: Final[tuple[StatementPage, ...]] = (
    StatementPage("income", "Income", "Income Statement", 1, _STATEMENT_DECL),
    StatementPage("balance", "Balance", "Balance Sheet", 2, _STATEMENT_DECL),
    StatementPage("cashflow", "Cash Flow", "Cash Flow Statement", 3, _STATEMENT_DECL),
)


def get_statement_page(slug: str) -> StatementPage | None:
    return next((p for p in STATEMENT_PAGES if p.slug == slug), None)
