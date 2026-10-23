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
class Greyed:
    """A Global Setting a page cannot honour.

    ``fixed`` is the value the page uses in its place, if it uses one.
    """

    reason: str
    fixed: SettingValue | None = None

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("a greyed Setting needs a reason")


@dataclass(frozen=True)
class CrossRule:
    ids: tuple[str, ...]
    holds: Callable[[Mapping[str, SettingValue]], bool]
    repair: Callable[[Mapping[str, SettingValue], int], Mapping[str, SettingValue]]
    message: str
