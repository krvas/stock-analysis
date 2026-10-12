import "./browser_globals.js";
import assert from "node:assert/strict";
import { test } from "node:test";

import { evaluate } from "../../src/static/js/components/calculated_cell.js";
import { TableModel } from "../../src/static/js/components/table_model.js";
import { loadFixture } from "./load_fixture.js";

test("Assets in Use gross and net evaluate to the adjustment engine's values", () => {
  const { table, expected } = loadFixture("assets_in_use_table.json");
  const model = TableModel.fromSerialized(table);
  const getCell = (rowId, colId) => model.getCell(rowId, colId);
  const specs = new Map(
    table.calculated_cells.map((spec) => [
      `${spec.row_id}/${spec.col_id}`,
      spec,
    ]),
  );
  assert.equal(expected.length, 4);
  for (const { row_id, col_id, value } of expected) {
    const spec = specs.get(`${row_id}/${col_id}`);
    assert.ok(spec, `no calculated cell for ${row_id}/${col_id}`);
    assert.equal(evaluate(spec.expr, getCell), value, `${row_id}/${col_id}`);
  }
});

const cells = { a: { x: 2, blank: null, empty: "", text: "3.5", bad: "n/a" } };
const getCell = (rowId, colId) => cells[rowId]?.[colId];
const ref = (colId) => ({ cell: ["a", colId] });

test("add sums and mul multiplies their arguments", () => {
  assert.equal(
    evaluate({ op: "add", args: [ref("x"), { const: 5 }] }, getCell),
    7,
  );
  assert.equal(
    evaluate({ op: "mul", args: [ref("x"), { const: 5 }] }, getCell),
    10,
  );
  assert.equal(evaluate({ op: "add", args: [] }, getCell), 0);
  assert.equal(evaluate({ op: "mul", args: [] }, getCell), 1);
});

test("nested expressions evaluate inside out", () => {
  const expr = {
    op: "add",
    args: [{ const: 1 }, { op: "mul", args: [{ const: -1 }, ref("x")] }],
  };
  assert.equal(evaluate(expr, getCell), -1);
});

test("a referenced cell that is blank, missing or non-numeric counts as 0", () => {
  for (const colId of ["blank", "empty", "bad", "missing"]) {
    assert.equal(evaluate(ref(colId), getCell), 0, colId);
  }
  assert.equal(evaluate(ref("text"), getCell), 3.5);
});

test("an unknown op throws", () => {
  assert.throws(
    () => evaluate({ op: "sub", args: [] }, getCell),
    /Unknown calculated-cell op: sub/,
  );
});
