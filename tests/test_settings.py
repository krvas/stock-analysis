from __future__ import annotations

import dataclasses
import json
from collections.abc import MutableMapping
from typing import cast

import pytest

from src.config import MAX_CACHE_QUARTERS, MAX_CACHE_YEARS, MAX_PERIODS_BY_PERIOD
from src.web.setting_types import Greyed
from src.web.settings import (
    NO_SETTINGS,
    SETTINGS,
    DrawerField,
    Refused,
    Saved,
    SettingNotApplicable,
    SettingsDecl,
    apply_submission,
    build_drawer,
    known_refusal,
    resolve,
    safe_next,
)
from src.web.settings_registry import GlobalSetting, SubpageSetting
from src.web.statements_registry import STATEMENT_PAGES
from src.web.wizard_registry import WIZARD_PAGES

FUND_FLOW_LIKE = SettingsDecl(
    uses=(
        SubpageSetting.BASIS,
        SubpageSetting.CURRENT_PERIOD,
        SubpageSetting.PREVIOUS_PERIOD,
    ),
    cannot_honour={GlobalSetting.NUM_PERIODS: Greyed("Two periods")},
)
PERIODS = [f"20{y:02d}-12-31" for y in range(24, 0, -1)]


def _cookie(**values: object) -> str:
    return json.dumps(values)


def test_defaults_on_a_fresh_browser() -> None:
    s = resolve(None, FUND_FLOW_LIKE)
    assert (
        s[GlobalSetting.PERIOD],
        s[GlobalSetting.VIEW],
        s[SubpageSetting.BASIS],
    ) == ("annual", "standard", "reported")
    assert s.period_at(SubpageSetting.CURRENT_PERIOD, PERIODS) == PERIODS[0]
    assert s.period_at(SubpageSetting.PREVIOUS_PERIOD, PERIODS) == PERIODS[1]
    bss = resolve(None, SettingsDecl(uses=(SubpageSetting.ITEMS_PER_SIDE,)))
    assert bss[SubpageSetting.ITEMS_PER_SIDE] == 5
    assert resolve(None, NO_SETTINGS)[GlobalSetting.NUM_PERIODS] == 10


def test_invalid_values_fall_back_per_field() -> None:
    s = resolve(
        _cookie(period="weekly", num_periods=3, view=7, basis="adjusted", junk=1),
        SettingsDecl(uses=(SubpageSetting.BASIS,)),
    )
    assert (
        s[GlobalSetting.PERIOD],
        s[GlobalSetting.NUM_PERIODS],
        s[GlobalSetting.VIEW],
        s[SubpageSetting.BASIS],
    ) == (
        "annual",
        3,
        "standard",
        "adjusted",
    )
    out_of_range = resolve(_cookie(num_periods=0, view="detailed"), NO_SETTINGS)
    assert (
        out_of_range[GlobalSetting.NUM_PERIODS],
        out_of_range[GlobalSetting.VIEW],
    ) == (10, "detailed")
    assert (
        resolve(_cookie(num_periods=True), NO_SETTINGS)[GlobalSetting.NUM_PERIODS] == 10
    )
    assert (
        resolve(_cookie(num_periods="4"), NO_SETTINGS)[GlobalSetting.NUM_PERIODS] == 4
    )


@pytest.mark.parametrize(
    "raw", ["{not json", "[1, 2]", '"annual"', "null", "", "[" * 5000]
)
def test_broken_or_non_object_cookie_gives_defaults(raw: str) -> None:
    s = resolve(raw, NO_SETTINGS)
    assert (
        s[GlobalSetting.PERIOD],
        s[GlobalSetting.NUM_PERIODS],
        s[GlobalSetting.VIEW],
    ) == ("annual", 10, "standard")


def test_greyed_and_undeclared_reads_raise() -> None:
    s = resolve(None, FUND_FLOW_LIKE)
    with pytest.raises(SettingNotApplicable):
        _ = s[GlobalSetting.NUM_PERIODS]
    with pytest.raises(SettingNotApplicable):
        _ = s[SubpageSetting.ITEMS_PER_SIDE]
    with pytest.raises(SettingNotApplicable):
        s.recent_periods(PERIODS)
    with pytest.raises(SettingNotApplicable):
        resolve(None, NO_SETTINGS).period_at(SubpageSetting.CURRENT_PERIOD, PERIODS)


def test_recent_periods_clamps_to_cap_and_available() -> None:
    assert (
        resolve(_cookie(num_periods=3), NO_SETTINGS).recent_periods(PERIODS)
        == (PERIODS[:3])
    )
    many = _cookie(num_periods=MAX_CACHE_QUARTERS)
    assert len(resolve(many, NO_SETTINGS).recent_periods(PERIODS)) == MAX_CACHE_YEARS
    quarterly = resolve(_cookie(period="quarterly", num_periods=40), NO_SETTINGS)
    assert quarterly.recent_periods(PERIODS) == PERIODS
    assert resolve(None, NO_SETTINGS).recent_periods(PERIODS[:2]) == PERIODS[:2]


def test_period_at_clamps_to_oldest_and_handles_empty() -> None:
    s = resolve(
        _cookie(period="quarterly", current_period=30, previous_period=40),
        FUND_FLOW_LIKE,
    )
    assert s.period_at(SubpageSetting.CURRENT_PERIOD, PERIODS) == PERIODS[-1]
    assert s.period_at(SubpageSetting.PREVIOUS_PERIOD, PERIODS[:3]) == PERIODS[2]
    assert s.period_at(SubpageSetting.CURRENT_PERIOD, []) is None


def test_failing_rule_keeps_current_and_repairs_previous() -> None:
    raw = _cookie(current_period=3, previous_period=1)
    s = resolve(raw, FUND_FLOW_LIKE)
    assert s.period_at(SubpageSetting.CURRENT_PERIOD, PERIODS) == PERIODS[3]
    assert s.period_at(SubpageSetting.PREVIOUS_PERIOD, PERIODS) == PERIODS[4]
    only_current = resolve(raw, SettingsDecl(uses=(SubpageSetting.CURRENT_PERIOD,)))
    assert only_current.period_at(SubpageSetting.CURRENT_PERIOD, PERIODS) == PERIODS[3]


@pytest.mark.parametrize("period", ["annual", "quarterly"])
def test_rule_holds_after_repair_even_at_the_oldest_offset(period: str) -> None:
    ceiling = MAX_PERIODS_BY_PERIOD[period] - 1
    s = resolve(
        _cookie(period=period, current_period=ceiling, previous_period=0),
        FUND_FLOW_LIKE,
    )
    current, previous = (
        s[SubpageSetting.CURRENT_PERIOD],
        s[SubpageSetting.PREVIOUS_PERIOD],
    )
    assert (current, previous) == (ceiling - 1, ceiling)
    fields = {
        f.setting.id: f for f in build_drawer(s, next_path="/", error=None).page_fields
    }
    for field in (fields["current_period"], fields["previous_period"]):
        assert field.value in {o.value for o in field.options}


def test_offsets_past_the_periods_a_page_can_serve_are_clamped_together() -> None:
    s = resolve(_cookie(current_period=20, previous_period=30), FUND_FLOW_LIKE)
    ceiling = MAX_CACHE_YEARS - 1
    assert s[SubpageSetting.CURRENT_PERIOD] == ceiling - 1
    assert s[SubpageSetting.PREVIOUS_PERIOD] == ceiling


def test_drawer_offers_only_offsets_the_period_type_can_serve() -> None:
    def last_offset(raw: str | None, decl: SettingsDecl) -> str:
        drawer = build_drawer(resolve(raw, decl), next_path="/", error=None)
        return drawer.page_fields[-1].options[-1].label

    assert last_offset(None, FUND_FLOW_LIKE) == f"{MAX_CACHE_YEARS - 1} yr back"
    quarterly = _cookie(period="quarterly")
    assert last_offset(quarterly, FUND_FLOW_LIKE) == (
        f"{MAX_CACHE_QUARTERS - 1} qtr back"
    )


def test_a_fixed_period_overrides_the_global_period_type() -> None:
    decl = SettingsDecl(
        uses=(SubpageSetting.CURRENT_PERIOD,),
        cannot_honour={GlobalSetting.PERIOD: Greyed("Annual only", fixed="annual")},
    )
    s = resolve(_cookie(period="quarterly", current_period=40), decl)
    assert s.period_type == "annual"
    assert s[SubpageSetting.CURRENT_PERIOD] == MAX_CACHE_YEARS - 1


def test_submission_merges_into_stored_values() -> None:
    stored = _cookie(period="quarterly", num_periods=20, basis="adjusted")
    out = apply_submission({"num_periods": "4", "next": "/wizard/T/a/b"}, stored)
    assert isinstance(out, Saved)
    assert out.redirect_to == "/wizard/T/a/b"
    assert json.loads(out.cookie_value) == {
        "period": "quarterly",
        "num_periods": 4,
        "basis": "adjusted",
    }


def test_submission_ignores_unknown_and_drops_invalid_stored() -> None:
    out = apply_submission({"view": "detailed", "x": "1"}, _cookie(period="weekly"))
    assert isinstance(out, Saved)
    assert json.loads(out.cookie_value) == {"view": "detailed"}


@pytest.mark.parametrize(
    "form",
    [
        {"num_periods": "0"},
        {"num_periods": ""},
        {"num_periods": "9" * 5000},
        {"period": "weekly"},
    ],
)
def test_invalid_submission_is_refused(form: dict[str, str]) -> None:
    out = apply_submission(form | {"next": "/statements/T/income"}, None)
    assert isinstance(out, Refused)
    assert out.redirect_to == "/statements/T/income"
    assert out.message


def test_rule_refuses_only_when_both_offsets_submitted() -> None:
    stored = _cookie(previous_period=1)
    refused = apply_submission(
        {"current_period": "2", "previous_period": "2", "next": "/p"}, stored
    )
    assert refused == Refused(
        "/p", "Previous period must be older than the current period"
    )
    out = apply_submission({"current_period": "3"}, stored)
    assert isinstance(out, Saved)
    assert json.loads(out.cookie_value) == {"previous_period": 1, "current_period": 3}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/statements/AAPL/income", "/statements/AAPL/income"),
        ("/wizard/AAPL?x=1", "/wizard/AAPL?x=1"),
        ("//evil.com", "/"),
        ("/\\evil.com", "/"),
        ("/\t/evil.com", "/"),
        ("https://x", "/"),
        ("evil.com/path", "/"),
        ("", "/"),
        (None, "/"),
    ],
)
def test_safe_next(raw: str | None, expected: str) -> None:
    assert safe_next(raw) == expected
    assert apply_submission({"next": raw} if raw else {}, None).redirect_to == expected


def test_a_greyed_setting_needs_a_reason() -> None:
    with pytest.raises(ValueError):
        Greyed("  ")


@pytest.mark.parametrize(
    ("decl", "error"),
    [
        ({"uses": ("basis",)}, TypeError),
        ({"uses": (GlobalSetting.PERIOD,)}, TypeError),
        ({"uses": (SubpageSetting.BASIS, SubpageSetting.BASIS)}, ValueError),
        ({"cannot_honour": {SubpageSetting.BASIS: Greyed("No")}}, TypeError),
        ({"cannot_honour": {"view": Greyed("Summary only")}}, TypeError),
        ({"cannot_honour": {GlobalSetting.VIEW: "Summary only"}}, TypeError),
        (
            {"cannot_honour": {GlobalSetting.PERIOD: Greyed("x", fixed="weekly")}},
            ValueError,
        ),
    ],
)
def test_bad_declaration_raises(decl: dict, error: type[Exception]) -> None:
    with pytest.raises(error):
        SettingsDecl(**decl)


def test_drawer_greys_globals_and_lists_declared_subpage_fields() -> None:
    decl = SettingsDecl(
        uses=(SubpageSetting.CURRENT_PERIOD, SubpageSetting.ITEMS_PER_SIDE),
        cannot_honour={GlobalSetting.VIEW: Greyed("Summary only")},
    )
    drawer = build_drawer(
        resolve(_cookie(view="detailed"), decl), next_path="/p", error="bad"
    )
    assert [f.setting for f in drawer.global_fields] == [s.value for s in GlobalSetting]
    view = drawer.global_fields[2]
    assert (view.disabled_reason, view.widget, view.value) == (
        "Summary only",
        "select",
        "detailed",
    )
    assert view.setting is GlobalSetting.VIEW.value
    assert [f.setting for f in drawer.page_fields] == [
        SubpageSetting.CURRENT_PERIOD.value,
        SubpageSetting.ITEMS_PER_SIDE.value,
    ]
    current, items = drawer.page_fields
    assert (current.widget, current.options[:2]) == (
        "select",
        (("0", "Latest"), ("1", "1 yr back")),
    )
    assert (items.widget, items.options, items.value) == ("number", (), "5")
    assert (drawer.next_path, drawer.error) == ("/p", "bad")
    assert (
        build_drawer(resolve(None, NO_SETTINGS), next_path="/", error=None).page_fields
        == ()
    )


def test_declared_greyed_settings_cannot_be_mutated() -> None:
    with pytest.raises(TypeError):
        mapping = cast(
            "MutableMapping[GlobalSetting, Greyed]", NO_SETTINGS.cannot_honour
        )
        mapping[GlobalSetting.VIEW] = Greyed("x")


def test_only_messages_the_server_writes_reach_the_drawer() -> None:
    assert known_refusal("Invalid number of periods") == "Invalid number of periods"
    assert known_refusal("Previous period must be older than the current period")
    assert known_refusal("<b>pay me</b>") is None
    assert known_refusal(None) is None


def test_every_default_is_valid() -> None:
    for setting in SETTINGS:
        assert setting.parse(setting.default) == setting.default


def _declarations() -> list[tuple[str, SettingsDecl]]:
    wizard = [
        (f"{page.slug}/{sub.slug}", sub.settings)
        for page in WIZARD_PAGES
        for sub in page.subpages
    ]
    return wizard + [(p.slug, p.settings) for p in STATEMENT_PAGES]


def test_every_page_declaration_names_registry_settings_with_reasons() -> None:
    declarations = _declarations()
    assert {name for name, _ in declarations} >= {
        "income",
        "balance",
        "cashflow",
        "business-understanding/balance-sheet-size",
    }
    for name, decl in declarations:
        assert isinstance(decl, SettingsDecl), name
        assert all(isinstance(s, SubpageSetting) for s in decl.uses), name
        for setting, greyed in decl.cannot_honour.items():
            assert isinstance(setting, GlobalSetting) and greyed.reason.strip(), name


def test_drawer_field_holds_only_what_it_renders() -> None:
    extra = {f.name for f in dataclasses.fields(DrawerField)} - {
        "setting",
        "value",
        "disabled_reason",
        "options",
    }
    assert not extra, (
        f"DrawerField gained {sorted(extra)}. Whatever depends on the page's "
        "Settings (the period type, a ceiling) is computed by Settings, e.g. "
        "Settings.options, and DrawerField receives the result."
    )


def test_settings_decl_holds_no_per_setting_field() -> None:
    extra = {f.name for f in dataclasses.fields(SettingsDecl)} - {
        "uses",
        "cannot_honour",
    }
    assert not extra, (
        f"SettingsDecl gained {sorted(extra)}. Information about one Setting "
        "belongs in that Setting's entry: a greyed Global Setting carries it "
        "in its Greyed value inside cannot_honour; a Sub-page Setting is in uses."
    )
