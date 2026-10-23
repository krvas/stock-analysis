from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final, Literal, cast

from src.config import MAX_PERIODS_BY_PERIOD
from src.models.statement import PeriodType
from src.web.setting_types import (
    ChoiceSetting,
    IntSetting,
    Option,
    SettingDef,
    SettingValue,
)
from src.web.settings_registry import RULES, GlobalSetting, SubpageSetting

SETTINGS: Final[tuple[SettingDef, ...]] = tuple(
    s.value for s in (*GlobalSetting, *SubpageSetting)
)
SettingKey = GlobalSetting | SubpageSetting
_BY_ID: Final[Mapping[str, SettingKey]] = {
    s.value.id: s for s in (*GlobalSetting, *SubpageSetting)
}

_OFFSET_UNIT: Final = {"annual": "yr", "quarterly": "qtr"}

if len({s.id for s in SETTINGS}) != len(SETTINGS):
    raise RuntimeError("Setting ids must be unique")
for _rule in RULES:
    if unknown := [i for i in _rule.ids if i not in _BY_ID]:
        raise RuntimeError(f"rule {_rule.message!r} names unknown Settings {unknown}")


def _invalid_message(setting: SettingDef) -> str:
    return f"Invalid {setting.label.lower()}"


def known_refusal(raw: str | None) -> str | None:
    """``raw`` if it is a message ``apply_submission`` can refuse with, else None."""
    known = {_invalid_message(s) for s in SETTINGS} | {r.message for r in RULES}
    return raw if raw in known else None


@dataclass(frozen=True)
class SettingsDecl:
    uses: tuple[SubpageSetting, ...] = ()
    cannot_honour: Mapping[GlobalSetting, str] = field(default_factory=dict)
    fixed_period: PeriodType | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "cannot_honour", MappingProxyType(dict(self.cannot_honour))
        )
        if self.fixed_period and GlobalSetting.PERIOD not in self.cannot_honour:
            raise ValueError("fixed_period needs the Period type greyed out")
        for setting in self.uses:
            if not isinstance(setting, SubpageSetting):
                raise TypeError(f"{setting!r} in uses is not a SubpageSetting")
        if len(set(self.uses)) != len(self.uses):
            raise ValueError(f"duplicate Setting in uses: {self.uses}")
        for setting, reason in self.cannot_honour.items():
            if not isinstance(setting, GlobalSetting):
                raise TypeError(f"{setting!r} in cannot_honour is not a GlobalSetting")
            if not reason.strip():
                raise ValueError(f"greyed {setting!r} needs a reason")

    def applies(self, setting: SettingKey) -> bool:
        if isinstance(setting, GlobalSetting):
            return setting not in self.cannot_honour
        return setting in self.uses


NO_SETTINGS: Final = SettingsDecl()


class SettingNotApplicable(LookupError):
    pass


def _period_type(decl: SettingsDecl, values: Mapping[str, SettingValue]) -> PeriodType:
    return decl.fixed_period or cast(PeriodType, values[GlobalSetting.PERIOD.value.id])


def _offset_ceiling(period_type: PeriodType) -> int:
    return MAX_PERIODS_BY_PERIOD[period_type] - 1


@dataclass(frozen=True)
class Settings:
    decl: SettingsDecl
    values: Mapping[str, SettingValue]

    def __getitem__(self, setting: SettingKey) -> SettingValue:
        if not self.decl.applies(setting):
            raise SettingNotApplicable(
                f"read of {setting!r}, which this page's SettingsDecl greys "
                "out or does not declare; declare it or stop reading it"
            )
        return self.values[setting.value.id]

    @property
    def period_type(self) -> PeriodType:
        return _period_type(self.decl, self.values)

    def recent_periods(self, available: Sequence[str]) -> list[str]:
        cap = MAX_PERIODS_BY_PERIOD[self[GlobalSetting.PERIOD]]
        return list(available[: min(self[GlobalSetting.NUM_PERIODS], cap)])

    def period_at(self, which: SubpageSetting, available: Sequence[str]) -> str | None:
        offset = self[which]
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
        s.value.id: stored.get(s.value.id, s.value.default)
        for s in (*GlobalSetting, *decl.uses)
    }
    ceiling = _offset_ceiling(_period_type(decl, values))
    for setting in decl.uses:
        if isinstance(setting.value, IntSetting) and setting.value.widget == "offset":
            values[setting.value.id] = min(cast(int, values[setting.value.id]), ceiling)
    for rule in RULES:
        if all(decl.applies(_BY_ID[i]) for i in rule.ids) and not rule.holds(values):
            values |= rule.repair(values, ceiling)
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
            return Refused(redirect_to, _invalid_message(setting))
        submitted[setting.id] = value
    merged = _stored_values(raw_cookie) | submitted
    for rule in RULES:
        if all(i in submitted for i in rule.ids) and not rule.holds(merged):
            return Refused(redirect_to, rule.message)
    return Saved(redirect_to, json.dumps(merged, separators=(",", ":")))


@dataclass(frozen=True)
class DrawerField:
    setting: SettingDef
    value: str
    disabled_reason: str | None
    period_type: PeriodType

    @property
    def widget(self) -> Literal["select", "number"]:
        if isinstance(self.setting, ChoiceSetting) or self.setting.widget == "offset":
            return "select"
        return "number"

    @property
    def options(self) -> tuple[Option, ...]:
        setting = self.setting
        if isinstance(setting, ChoiceSetting):
            return setting.options
        if setting.widget == "offset":
            unit = _OFFSET_UNIT[self.period_type]
            return tuple(
                Option(str(i), "Latest" if i == 0 else f"{i} {unit} back")
                for i in range(
                    setting.min,
                    min(setting.max, _offset_ceiling(self.period_type)) + 1,
                )
            )
        return ()


@dataclass(frozen=True)
class Drawer:
    global_fields: tuple[DrawerField, ...]
    page_fields: tuple[DrawerField, ...]
    next_path: str
    error: str | None


def build_drawer(settings: Settings, *, next_path: str, error: str | None) -> Drawer:
    decl = settings.decl
    period_type = settings.period_type
    global_fields = tuple(
        DrawerField(
            s.value,
            str(settings.values[s.value.id]),
            decl.cannot_honour.get(s),
            period_type,
        )
        for s in GlobalSetting
    )
    page_fields = tuple(
        DrawerField(s.value, str(settings.values[s.value.id]), None, period_type)
        for s in SubpageSetting
        if s in decl.uses
    )
    return Drawer(global_fields, page_fields, next_path, error)
