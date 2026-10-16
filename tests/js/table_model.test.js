import "./browser_globals.js";
import assert from "node:assert/strict";
import { test } from "node:test";

import { TableModel } from "../../src/static/js/components/table_model.js";
import { loadFixture } from "./load_fixture.js";

const { table } = loadFixture("assets_in_use_table.json");
const PERIOD = table.columns[0].id;

function model() {
  return TableModel.fromSerialized(table);
}

test("fromSerialized exposes every row, column and cell of the payload", () => {
  const m = model();
  assert.deepEqual(
    m.rows.map((row) => row.id),
    table.rows.map((row) => row.id),
  );
  assert.deepEqual(m.columns, table.columns);
  for (const row of table.rows) {
    for (const [colId, value] of Object.entries(row.cells)) {
      assert.equal(m.getCell(row.id, colId), value, `${row.id}/${colId}`);
    }
  }
  assert.deepEqual(m.calculated_cells, table.calculated_cells);
  assert.deepEqual(m.no_input_cells, table.no_input_cells);
});

test("getCell on an unknown row is undefined", () => {
  assert.equal(model().getCell("no-such-row", PERIOD), undefined);
});

test("setCell stores the value and notifies subscribers until unsubscribed", () => {
  const m = model();
  const seen = [];
  const unsubscribe = m.subscribe((...args) => seen.push(args));

  m.setCell("Construction", "pct_in_use", 40);
  assert.equal(m.getCell("Construction", "pct_in_use"), 40);
  assert.deepEqual(seen, [["Construction", "pct_in_use", 40]]);

  unsubscribe();
  m.setCell("Construction", "pct_in_use", 60);
  assert.equal(m.getCell("Construction", "pct_in_use"), 60);
  assert.equal(seen.length, 1);
});

test("setCell rejects an unknown row or column without notifying", () => {
  const m = model();
  const seen = [];
  m.subscribe((...args) => seen.push(args));
  assert.throws(() => m.setCell("no-such-row", "pct_in_use", 1), /row id/);
  assert.throws(() => m.setCell("Cash", "no-such-col", 1), /column id/);
  assert.deepEqual(seen, []);
});

test("serialize sends only input columns and their cells, not the received shape", () => {
  const m = model();
  m.setCell("Construction", "pct_in_use", 25);
  m.setCell("Payables", "net_out", false);
  const body = m.serialize();

  assert.deepEqual(Object.keys(body).sort(), ["columns", "rows"]);
  assert.deepEqual(
    body.columns.map((col) => col.id),
    ["pct_in_use", "net_out"],
  );
  assert.deepEqual(
    body.rows.map((row) => row.id),
    table.rows.map((row) => row.id),
  );
  for (const row of body.rows) {
    assert.deepEqual(Object.keys(row).sort(), ["cells", "id"]);
    assert.deepEqual(Object.keys(row.cells), ["pct_in_use", "net_out"]);
  }
  const byId = Object.fromEntries(body.rows.map((row) => [row.id, row.cells]));
  assert.deepEqual(byId.Construction, { pct_in_use: 25, net_out: null });
  assert.deepEqual(byId.Payables, { pct_in_use: null, net_out: false });
});
