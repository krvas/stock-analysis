"""The shapes of wizard and statement pages.

Pure types; ``src/web/wizard_registry.py`` and
``src/web/statements_registry.py`` hold the actual pages.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final, Literal

from src.models.statement import StatementType
from src.web.settings import NO_SETTINGS, Settings, SettingsDecl

PageGroup = Literal["business", "people", "price", "red_flags"]

SubPageContextBuilder = Callable[[str, Settings], dict[str, Any]]
default_context_builder: Final[SubPageContextBuilder] = lambda ticker, settings: {}

SubPagePostHandler = Callable[[str, dict[str, Any]], dict[str, Any]]
default_post_handler: Final[SubPagePostHandler | None] = None


@dataclass(frozen=True)
class SubPage:
    slug: str
    title: str
    order: int
    context_builder: SubPageContextBuilder = default_context_builder
    post_handler: SubPagePostHandler | None = default_post_handler
    settings: SettingsDecl = NO_SETTINGS


@dataclass(frozen=True)
class Page:
    slug: str
    title: str
    order: int
    group: PageGroup
    subpages: list[SubPage]


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
