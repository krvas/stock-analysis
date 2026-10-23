"""The shapes of a Setting and of a rule over several Settings.

Pure types with no registry knowledge; ``src/web/settings_registry.py`` holds
the actual Settings and rules.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal, NamedTuple

SettingValue = str | int


class Option(NamedTuple):
    value: str
    label: str


@dataclass(frozen=True)
class ChoiceSetting:
    id: str
    label: str
    options: tuple[Option, ...]
    default: str
    instant: bool = False

    def parse(self, raw: object) -> str | None:
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
    widget: Literal["number", "offset"] = "number"
    instant: bool = False

    def parse(self, raw: object) -> int | None:
        if isinstance(raw, bool):
            return None
        if isinstance(raw, str):
            if not (raw.isascii() and raw.isdigit()) or len(raw) > len(str(self.max)):
                return None
            raw = int(raw)
        if isinstance(raw, int) and self.min <= raw <= self.max:
            return raw
        return None


SettingDef = ChoiceSetting | IntSetting


@dataclass(frozen=True)
class CrossRule:
    ids: tuple[str, ...]
    holds: Callable[[Mapping[str, SettingValue]], bool]
    # Second argument: the highest offset the page can serve.
    repair: Callable[[Mapping[str, SettingValue], int], Mapping[str, SettingValue]]
    message: str
