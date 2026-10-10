from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final, Literal, NamedTuple, cast, get_args

from src.config import MAX_CACHE_QUARTERS, MAX_ITEMS_PER_SIDE, MAX_PERIODS_BY_PERIOD
from src.models.statement import (
    PERIOD_TYPES,
    STATEMENT_VIEWS,
    PeriodType,
    StatementView,
)

GlobalSettingId = Literal["period", "num_periods", "view"]
SubpageSettingId = Literal[
    "basis", "current_period", "previous_period", "items_per_side"
]
SettingId = GlobalSettingId | SubpageSettingId
OffsetSettingId = Literal["current_period", "previous_period"]
Basis = Literal["reported", "adjusted"]
SettingValue = str | int

GLOBAL_SETTING_IDS: Final[frozenset[str]] = frozenset(get_args(GlobalSettingId))
SUBPAGE_SETTING_IDS: Final[frozenset[str]] = frozenset(get_args(SubpageSettingId))


class Option(NamedTuple):
    value: str
    label: str


@dataclass(frozen=True)
class ChoiceSetting:
    id: SettingId
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
    id: SettingId
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
            if not (raw.isascii() and raw.isdigit()):
                return None
            raw = int(raw)
        if isinstance(raw, int) and self.min <= raw <= self.max:
            return raw
        return None


SettingDef = ChoiceSetting | IntSetting

SETTINGS: Final[tuple[SettingDef, ...]] = (
    ChoiceSetting(
        "period",
        "Period type",
        tuple(Option(p, p.capitalize()) for p in PERIOD_TYPES),
        "annual",
    ),
    IntSetting("num_periods", "Number of periods", 1, MAX_CACHE_QUARTERS, 10),
    ChoiceSetting(
        "view",
        "View",
        tuple(Option(v, v.capitalize()) for v in STATEMENT_VIEWS),
        "standard",
        instant=True,
    ),
    ChoiceSetting(
        "basis",
        "Basis",
        (Option("reported", "Reported"), Option("adjusted", "Adjusted")),
        "reported",
    ),
    IntSetting(
        "current_period",
        "Current period",
        0,
        MAX_CACHE_QUARTERS - 1,
        0,
        widget="offset",
    ),
    IntSetting(
        "previous_period",
        "Previous period",
        0,
        MAX_CACHE_QUARTERS - 1,
        1,
        widget="offset",
    ),
    IntSetting("items_per_side", "Items per side", 1, MAX_ITEMS_PER_SIDE, 5),
)
SETTINGS_BY_ID: Final[Mapping[str, SettingDef]] = MappingProxyType(
    {s.id: s for s in SETTINGS}
)

if set(SETTINGS_BY_ID) != GLOBAL_SETTING_IDS | SUBPAGE_SETTING_IDS or len(
    SETTINGS_BY_ID
) != len(SETTINGS):
    raise RuntimeError(
        "SETTINGS ids must match GlobalSettingId | SubpageSettingId exactly"
    )


def _keep_current_move_previous_back(
    values: Mapping[str, SettingValue],
) -> Mapping[str, SettingValue]:
    return {"previous_period": cast(int, values["current_period"]) + 1}


@dataclass(frozen=True)
class CrossRule:
    ids: tuple[SettingId, ...]
    holds: Callable[[Mapping[str, SettingValue]], bool]
    repair: Callable[[Mapping[str, SettingValue]], Mapping[str, SettingValue]]
    message: str


RULES: Final[tuple[CrossRule, ...]] = (
    CrossRule(
        ids=("current_period", "previous_period"),
        holds=lambda v: (
            cast(int, v["previous_period"]) > cast(int, v["current_period"])
        ),
        repair=_keep_current_move_previous_back,
        message="Previous period must be older than the current period",
    ),
)


@dataclass(frozen=True)
class SettingsDecl:
    uses: tuple[SubpageSettingId, ...] = ()
    cannot_honour: Mapping[GlobalSettingId, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for setting_id in self.uses:
            if setting_id not in SUBPAGE_SETTING_IDS:
                raise ValueError(f"{setting_id!r} in uses is not a Sub-page Setting")
        if len(set(self.uses)) != len(self.uses):
            raise ValueError(f"duplicate id in uses: {self.uses}")
        for setting_id, reason in self.cannot_honour.items():
            if setting_id not in GLOBAL_SETTING_IDS:
                raise ValueError(
                    f"{setting_id!r} in cannot_honour is not a Global Setting"
                )
            if not reason.strip():
                raise ValueError(f"greyed {setting_id!r} needs a reason")

    def applies(self, setting_id: str) -> bool:
        if setting_id in GLOBAL_SETTING_IDS:
            return setting_id not in self.cannot_honour
        return setting_id in self.uses


NO_SETTINGS: Final = SettingsDecl()


class SettingNotApplicable(LookupError):
    pass


@dataclass(frozen=True)
class Settings:
    decl: SettingsDecl
    values: Mapping[str, SettingValue]

    def _read(self, setting_id: SettingId) -> SettingValue:
        if not self.decl.applies(setting_id):
            raise SettingNotApplicable(
                f"read of {setting_id!r}, which this page's SettingsDecl greys "
                "out or does not declare; declare it or stop reading it"
            )
        return self.values[setting_id]

    @property
    def period(self) -> PeriodType:
        return cast(PeriodType, self._read("period"))

    @property
    def num_periods(self) -> int:
        return cast(int, self._read("num_periods"))

    @property
    def view(self) -> StatementView:
        return cast(StatementView, self._read("view"))

    @property
    def basis(self) -> Basis:
        return cast(Basis, self._read("basis"))

    @property
    def items_per_side(self) -> int:
        return cast(int, self._read("items_per_side"))

    def recent_periods(self, available: Sequence[str]) -> list[str]:
        count = min(self.num_periods, MAX_PERIODS_BY_PERIOD[self.period])
        return list(available[:count])

    def period_at(self, which: OffsetSettingId, available: Sequence[str]) -> str | None:
        offset = cast(int, self._read(which))
        if not available:
            return None
        return available[min(offset, len(available) - 1)]


def _stored_values(raw_cookie: str | None) -> dict[str, SettingValue]:
    if not raw_cookie:
        return {}
    try:
        stored = json.loads(raw_cookie)
    except (ValueError, RecursionError):
        return {}
    if not isinstance(stored, dict):
        return {}
    values: dict[str, SettingValue] = {}
    for setting in SETTINGS:
        value = setting.parse(stored.get(setting.id))
        if value is not None:
            values[setting.id] = value
    return values


def resolve(raw_cookie: str | None, decl: SettingsDecl) -> Settings:
    stored = _stored_values(raw_cookie)
    values: dict[str, SettingValue] = {
        s.id: stored.get(s.id, s.default)
        for s in SETTINGS
        if s.id in GLOBAL_SETTING_IDS or s.id in decl.uses
    }
    for rule in RULES:
        if all(decl.applies(i) for i in rule.ids) and not rule.holds(values):
            values |= rule.repair(values)
    return Settings(decl=decl, values=MappingProxyType(values))


def safe_next(raw: str | None) -> str:
    if (
        not raw
        or not raw.startswith("/")
        or raw.startswith("//")
        or "\\" in raw
        or any(ord(c) < 0x20 or ord(c) == 0x7F for c in raw)
    ):
        return "/"
    return raw


@dataclass(frozen=True)
class Saved:
    redirect_to: str
    cookie_value: str


@dataclass(frozen=True)
class Refused:
    redirect_to: str
    message: str


SaveOutcome = Saved | Refused


def apply_submission(form: Mapping[str, str], raw_cookie: str | None) -> SaveOutcome:
    redirect_to = safe_next(form.get("next"))
    submitted: dict[str, SettingValue] = {}
    for setting in SETTINGS:
        if setting.id not in form:
            continue
        value = setting.parse(form[setting.id])
        if value is None:
            return Refused(redirect_to, f"Invalid {setting.label.lower()}")
        submitted[setting.id] = value
    merged = _stored_values(raw_cookie) | submitted
    for rule in RULES:
        if all(i in submitted for i in rule.ids) and not rule.holds(merged):
            return Refused(redirect_to, rule.message)
    return Saved(redirect_to, json.dumps(merged, separators=(",", ":")))


@dataclass(frozen=True)
class DrawerField:
    id: str
    label: str
    widget: Literal["select", "number"]
    options: tuple[Option, ...]
    min: int | None
    max: int | None
    value: str
    instant: bool
    disabled_reason: str | None


@dataclass(frozen=True)
class Drawer:
    global_fields: tuple[DrawerField, ...]
    page_fields: tuple[DrawerField, ...]
    next_path: str
    error: str | None


def _offset_label(offset: int) -> str:
    return "Latest" if offset == 0 else f"{offset} back"


def _drawer_field(
    setting: SettingDef, value: SettingValue, reason: str | None
) -> DrawerField:
    if isinstance(setting, ChoiceSetting):
        widget, options, low, high = "select", setting.options, None, None
    elif setting.widget == "offset":
        widget, low, high = "select", None, None
        options = tuple(
            Option(str(i), _offset_label(i))
            for i in range(setting.min, setting.max + 1)
        )
    else:
        widget, options, low, high = "number", (), setting.min, setting.max
    return DrawerField(
        id=setting.id,
        label=setting.label,
        widget=widget,
        options=options,
        min=low,
        max=high,
        value=str(value),
        instant=setting.instant,
        disabled_reason=reason,
    )


def build_drawer(settings: Settings, *, next_path: str, error: str | None) -> Drawer:
    decl = settings.decl
    global_fields = tuple(
        _drawer_field(s, settings.values[s.id], decl.cannot_honour.get(s.id))
        for s in SETTINGS
        if s.id in GLOBAL_SETTING_IDS
    )
    page_fields = tuple(
        _drawer_field(s, settings.values[s.id], None)
        for s in SETTINGS
        if s.id in decl.uses
    )
    return Drawer(global_fields, page_fields, next_path, error)
