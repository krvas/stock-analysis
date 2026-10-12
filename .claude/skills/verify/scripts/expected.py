from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from src.adjustments.base import AdjustmentSpec
from src.adjustments.types import assets_in_use as aiu
from src.database import wizard_manager
from src.web.adjusted_statements import load_adjusted
from src.web.routes.statements import statement_context
from src.web.routes.wizard_pages import assets_in_use as aiu_page
from src.web.routes.wizard_pages import business_understanding as bu
from src.web.settings import Settings, SettingsDecl, resolve
from src.web.statements_registry import STATEMENT_PAGES, StatementPage
from src.web.wizard_registry import get_subpage

Expectation = dict[str, Any]


def _cells(table: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["id"]: {"label": row["label"], **row["cells"]} for row in table["rows"]}


def _unique_largest(rows: list[dict[str, Any]], period: str) -> dict[str, Any]:
    labels = [row["label"] for row in rows]
    unique = [r for r in rows if labels.count(r["label"]) == 1 and r[period]]
    pick = max(unique, key=lambda r: abs(r[period]))
    return {"row_id": pick["row_id"], "label": pick["label"], "value": pick[period]}


def assets_in_use(
    ticker: str, settings: Settings, args: argparse.Namespace
) -> Expectation:
    _, staged, specs = load_adjusted(ticker, "annual", until=aiu.TYPE_ID)
    saved = next((dict(s.params) for s in specs if s.type_id == aiu.TYPE_ID), {})
    params = saved | dict(args.pct) | {row: aiu.NETTED for row in args.net}
    memo = aiu.apply(staged, AdjustmentSpec(aiu.TYPE_ID, params)).new_rows
    table = aiu_page.assets_in_use_context(ticker, settings)["aiu_table"]
    inputs = {col.id for col in aiu_page.INPUT_COLUMNS}
    periods = [c["id"] for c in table["columns"] if c["id"] not in inputs]
    expect = {
        row_id: {k: v for k, v in cells.items() if k not in inputs}
        for row_id, cells in _cells(table).items()
    }
    for row_id, row in zip((aiu_page.GROSS_ROW, aiu_page.NET_ROW), memo, strict=True):
        expect[row_id] |= {p: row.values.get(p) for p in periods}
    sides = aiu_page.side_rows(staged.balance, periods[:1])
    return {
        "table": "aiu-table",
        "choices": params,
        "targets": {
            "asset": _unique_largest(sides["assets"].to_dict("records"), periods[0]),
            "liability": _unique_largest(
                sides["liabilities"].to_dict("records"), periods[0]
            ),
        },
        "expect": expect,
    }


def fund_flow(ticker: str, settings: Settings, _: argparse.Namespace) -> Expectation:
    context = bu.fund_flow_context(ticker, settings)
    if "fund_flow_table" not in context:
        return {"table": None, "not_enough_periods": True}
    return {"table": "fund-flow-table", "expect": _cells(context["fund_flow_table"])}


def balance_sheet_size(
    ticker: str, settings: Settings, _: argparse.Namespace
) -> Expectation:
    context = bu.balance_sheet_size_context(ticker, settings)
    return {
        "as_of": context["as_of"],
        "treemaps": {
            side: [
                {"row_id": r["id"], "label": r["label"], "value": r["cells"]["value"]}
                for r in table["rows"]
            ]
            for side, table in context.get("sides", {}).items()
        },
    }


def _statement(page: StatementPage) -> Callable[..., Expectation]:
    def expected(ticker: str, settings: Settings, _: argparse.Namespace) -> Expectation:
        table = statement_context(ticker, page, settings)["statement_table"]
        return {"table": "statement-table", "expect": _cells(table)}

    return expected


PAGES: dict[str, tuple[Callable[..., Expectation], SettingsDecl]] = {
    "assets-in-use": (
        assets_in_use,
        get_subpage("adjustments", "assets-in-use").settings,
    ),
    "fund-flow": (
        fund_flow,
        get_subpage("business-understanding", "fund-flow").settings,
    ),
    "balance-sheet-size": (
        balance_sheet_size,
        get_subpage("business-understanding", "balance-sheet-size").settings,
    ),
    **{page.slug: (_statement(page), page.settings) for page in STATEMENT_PAGES},
}

CHECK_TABLE_JS = """\
((tableId, expect) => {
  const fmt = (v) => v == null ? "—"
    : (v / 1e6).toLocaleString(undefined, { maximumFractionDigits: 0 });
  const data = JSON.parse(document.getElementById(`${tableId}-data`).textContent);
  const cols = data.columns.map((c) => c.id);
  const trs = [...document.getElementById(tableId).tBodies[0].rows];
  const page = {};
  data.rows.forEach((row, i) => {
    const tds = [...trs[i].cells];
    page[row.id] = { label: tds[0].textContent };
    cols.forEach((col, j) => { page[row.id][col] = tds[j + 1].textContent.trim(); });
  });
  const mismatches = [];
  let checked = 0;
  for (const [rowId, want] of Object.entries(expect)) {
    for (const [col, value] of Object.entries(want)) {
      const got = page[rowId]?.[col];
      const wanted = col === "label" ? value : fmt(value);
      checked += 1;
      if (got !== wanted) mismatches.push({ rowId, col, wanted, got });
    }
  }
  const unchecked = Object.keys(page).filter((id) => !(id in expect)).length;
  return { checked, mismatches, rows_on_page: data.rows.length, unchecked };
})(%s, %s)"""

CHECK_TREEMAP_JS = """\
((asOf, expect) => {
  const fmt = (v) => `$${(v / 1e9).toFixed(1)}B`;
  const out = { checked: 1, mismatches: [] };
  const note = document.querySelector(".wizard-table-note")?.textContent;
  if (note !== `As of ${asOf}`) out.mismatches.push({ wanted: `As of ${asOf}`, got: note });
  for (const [side, items] of Object.entries(expect)) {
    const boxes = [...document.querySelectorAll(`[data-treemap="${side}"] .treemap-box`)]
      .map((b) => ({ label: b.querySelector("strong").textContent,
                     value: b.querySelector("span").textContent,
                     area: parseFloat(b.style.width) * parseFloat(b.style.height) }));
    if (boxes.length !== items.length)
      out.mismatches.push({ side, wanted_count: items.length, got_count: boxes.length });
    items.forEach((item, i) => {
      out.checked += 1;
      const got = boxes[i];
      if (!got || got.label !== item.label || got.value !== fmt(item.value))
        out.mismatches.push({ side, i, wanted: [item.label, fmt(item.value)],
                              got: got && [got.label, got.value] });
    });
    const total = items.reduce((s, it) => s + it.value, 0);
    boxes.forEach((b, i) => {
      if (items[i] && Math.abs(b.area / 1e4 - items[i].value / total) > 1e-6)
        out.mismatches.push({ side, i, area_share: b.area / 1e4,
                              wanted_share: items[i].value / total });
    });
  }
  return out;
})(%s, %s)"""


def _js(expectation: Expectation) -> str:
    if "treemaps" in expectation:
        return CHECK_TREEMAP_JS % (
            json.dumps(expectation["as_of"]),
            json.dumps(expectation["treemaps"]),
        )
    return CHECK_TABLE_JS % (
        json.dumps(expectation["table"]),
        json.dumps(expectation["expect"]),
    )


def _pct(raw: str) -> tuple[str, float]:
    row_id, _, pct = raw.rpartition("=")
    return row_id, float(pct)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("ticker", type=str.upper)
    parser.add_argument("page", choices=PAGES)
    parser.add_argument("--settings", default="{}")
    parser.add_argument("--pct", type=_pct, action="append", default=[])
    parser.add_argument("--net", action="append", default=[])
    parser.add_argument("--rows", type=lambda raw: raw.split(","))
    parser.add_argument("--js", action="store_true")
    args = parser.parse_args()

    db = args.run_dir / "wizard.duckdb"
    if not db.exists():
        parser.error(f"{db} not found: start the run with serve.py first")
    wizard_manager.DEFAULT_WIZARD_DB_PATH = db
    build, decl = PAGES[args.page]
    expectation = build(args.ticker, resolve(args.settings, decl), args)
    if args.rows and "expect" in expectation:
        expect = expectation["expect"]
        expectation["expect"] = {row: expect[row] for row in args.rows}
    print(_js(expectation) if args.js else json.dumps(expectation, indent=1))


if __name__ == "__main__":
    main()
