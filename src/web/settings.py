"""Settings: the registry of display choices and the pure rules around it.

Defines every Setting once (``SETTINGS``), the per-page declaration type
(``SettingsDecl``), the resolved ``Settings`` builders read, and the pure
entry points the HTTP shell in ``src/web/routes/settings.py`` calls:
``resolve`` (cookie + declaration -> Settings), ``apply_submission`` (form +
cookie -> new cookie value or a refusal) and ``build_drawer``. Nothing here
knows the cookie's name, HTTP, or any specific page.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final, Literal, cast, get_args

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


@dataclass(frozen=True)
class ChoiceSetting:
    id: SettingId
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
    id: SettingId
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

SETTINGS: Final[tuple[SettingDef, ...]] = (
    ChoiceSetting(
        "period",
        "Period type",
        tuple((p, p.capitalize()) for p in PERIOD_TYPES),
        "annual",
    ),
    # The per-period-type cache cap is a clamp at load time, not a validation
    # bound, so switching period type never invalidates the stored count.
    IntSetting("num_periods", "Number of periods", 1, MAX_CACHE_QUARTERS, 10),
    ChoiceSetting(
        "view",
        "View",
        tuple((v, v.capitalize()) for v in STATEMENT_VIEWS),
        "standard",
        instant=True,
    ),
    ChoiceSetting(
        "basis",
        "Basis",
        (("reported", "Reported"), ("adjusted", "Adjusted")),
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


@dataclass(frozen=True)
class CrossRule:
    """A rule over several Settings. It binds only where all its ids are in play.

    ``repair`` gives the values that make a failing rule hold for one render
    (``resolve``); a submission that breaks the rule is refused instead.
    """

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
        # Keep the current period: pages share it, so it must not move.
        repair=lambda v: {"previous_period": cast(int, v["current_period"]) + 1},
        message="Previous period must be older than the current period",
    ),
)


@dataclass(frozen=True)
class SettingsDecl:
    """Which Sub-page Settings a page uses and which Global Settings it greys out.

    The default instance uses none and honours every Global Setting.
    """

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
        """True when the page honours (Global) or declares (Sub-page) it."""
        if setting_id in GLOBAL_SETTING_IDS:
            return setting_id not in self.cannot_honour
        return setting_id in self.uses


NO_SETTINGS: Final = SettingsDecl()


class SettingNotApplicable(LookupError):
    """A builder read a Setting its page does not declare or greys out."""


@dataclass(frozen=True)
class Settings:
    """Resolved Settings for one page render; every value is valid.

    ``values`` holds every Global Setting (greyed ones too, for the drawer)
    and the page's declared Sub-page Settings. Reads of a greyed or
    undeclared Setting raise, so a builder cannot silently disagree with its
    page's declaration.
    """

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
        """The newest ``num_periods`` of ``available`` (newest first), clamped
        to the period type's cache cap and to what is available."""
        count = min(self.num_periods, MAX_PERIODS_BY_PERIOD[self.period])
        return list(available[:count])

    def period_at(self, which: OffsetSettingId, available: Sequence[str]) -> str | None:
        """The period ``which`` points at in ``available`` (newest first),
        clamped to the oldest one; None when nothing is available."""
        offset = cast(int, self._read(which))
        if not available:
            return None
        return available[min(offset, len(available) - 1)]


def _stored_values(raw_cookie: str | None) -> dict[str, SettingValue]:
    """The valid entries of a stored cookie value; anything else is dropped."""
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
    """Settings for a page from the raw cookie value and its declaration.

    Per field, a missing, unknown or invalid value falls back to the default.
    A failing rule whose ids all apply here is repaired for this render.
    Never raises on any cookie value, and never rewrites the cookie.
    """
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
    """``raw`` when it is a same-site path, else ``"/"``."""
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
    """The cookie stays unchanged; ``message`` is shown in the drawer."""

    redirect_to: str
    message: str


SaveOutcome = Saved | Refused


def apply_submission(form: Mapping[str, str], raw_cookie: str | None) -> SaveOutcome:
    """Validate a drawer submission and merge it into the stored Settings.

    ``form`` is the decoded POST body, including ``next``. Unknown keys are
    ignored; fields not submitted (greyed inputs are disabled, so never
    submitted) keep their stored value. A rule is checked only when every one
    of its ids was submitted, since a page that shows one of them cannot fix
    the other.
    """
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
    options: tuple[tuple[str, str], ...]
    min: int | None
    max: int | None
    value: str
    instant: bool
    disabled_reason: str | None


@dataclass(frozen=True)
class Drawer:
    global_fields: tuple[DrawerField, ...]
    # Empty -> the "This page" section is absent.
    page_fields: tuple[DrawerField, ...]
    next_path: str
    # Set -> the drawer opens on load showing it.
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
            (str(i), _offset_label(i)) for i in range(setting.min, setting.max + 1)
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
    """The drawer for a page, in registry order: every Global Setting (greyed
    ones carry their reason) and the page's declared Sub-page Settings."""
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
