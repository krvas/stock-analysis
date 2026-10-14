"""The shapes of a Setting and of a rule over several Settings.

Pure types with no registry knowledge; ``src/web/settings_registry.py`` holds
the actual Settings and rules.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal

SettingValue = str | int


@dataclass(frozen=True)
class ChoiceSetting:
    id: str
    label: str
    options: tuple[tuple[str, str], ...]  # (value, display label), drawer order
    default: str
    # Applies as soon as it changes (own form, submits on change).
    instant: bool = False

    def parse(self, raw: object) -> str | None:
        """``raw`` if it is one of the option values, else None."""
        if isinstance(raw, str) and any(raw == value for value, _ in self.options):
            return raw
        return None


@dataclass(frozen=True)
class IntSetting:
    id: str
    label: str
    min: int
    max: int
    default: int
    # "offset" renders as a select of "Latest", "1 back", ...
    widget: Literal["number", "offset"] = "number"
    instant: bool = False

    def parse(self, raw: object) -> int | None:
        """``raw`` as an int in ``[min, max]`` (an int or ASCII-digit str), else None."""
        if isinstance(raw, bool):
            return None
        if isinstance(raw, str):
            if not (raw.isascii() and raw.isdigit()):
                return None
            raw = int(raw)
        if isinstance(raw, int) and self.min <= raw <= self.max:
            return raw
        return None


SettingDef = ChoiceSetting | IntSetting


@dataclass(frozen=True)
class CrossRule:
    """A rule over several Settings. It binds only where all its ids are in play.

    ``repair`` gives the values that make a failing rule hold for one render
    (``resolve``); a submission that breaks the rule is refused instead.
    """

    ids: tuple[str, ...]
    holds: Callable[[Mapping[str, SettingValue]], bool]
    repair: Callable[[Mapping[str, SettingValue]], Mapping[str, SettingValue]]
    message: str
