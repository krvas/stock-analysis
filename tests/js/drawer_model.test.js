import assert from "node:assert/strict";
import { test } from "node:test";

import { DrawerModel } from "../../src/static/js/components/drawer_model.js";

function field(id, overrides = {}) {
  return {
    id,
    label: id,
    widget: "select",
    value: "a",
    instant: false,
    disabled_reason: null,
    options: [],
    min: null,
    max: null,
    ...overrides,
  };
}

function drawer(overrides = {}) {
  return DrawerModel.fromSerialized({
    next_path: "/statements/AAPL/income",
    error: null,
    global_fields: [
      field("period", { value: "annual" }),
      field("num_periods", { widget: "number", value: "10" }),
      field("view", { value: "standard", instant: true }),
    ],
    page_fields: [field("basis", { value: "reported" })],
    ...overrides,
  });
}

test("opens on load only when the server refused a save", () => {
  assert.equal(drawer().isOpen(), false);
  assert.equal(drawer({ error: "Invalid view" }).isOpen(), true);
});

test("setOpen notifies once per real change", () => {
  const model = drawer();
  const changes = [];
  model.subscribe((change) => changes.push(change));
  model.setOpen(true);
  model.setOpen(true);
  model.setOpen(false);
  assert.deepEqual(changes, [
    { type: "open", open: true },
    { type: "open", open: false },
  ]);
});

test("setValue stores and notifies, skipping unchanged values", () => {
  const model = drawer();
  const changes = [];
  model.subscribe((change) => changes.push(change));
  model.setValue("num_periods", 3);
  model.setValue("num_periods", 3);
  assert.equal(model.getValue("num_periods"), 3);
  assert.deepEqual(changes, [{ type: "value", id: "num_periods", value: 3 }]);
  assert.throws(() => model.setValue("bogus", 1), /Unknown drawer field: bogus/);
});

test("serialize sends the Apply group or the instant group, with next", () => {
  const model = drawer();
  model.setValue("num_periods", 3);
  assert.deepEqual(model.serialize({ instant: false }), {
    next: "/statements/AAPL/income",
    period: "annual",
    num_periods: "3",
    basis: "reported",
  });
  assert.deepEqual(model.serialize({ instant: true }), {
    next: "/statements/AAPL/income",
    view: "standard",
  });
});

test("serialize leaves out greyed fields and sends a cleared number as empty", () => {
  const model = drawer({
    global_fields: [
      field("period", { value: "annual", disabled_reason: "Annual only" }),
      field("num_periods", { widget: "number", value: "10" }),
    ],
    page_fields: [],
  });
  model.setValue("num_periods", null);
  assert.deepEqual(model.serialize({ instant: false }), {
    next: "/statements/AAPL/income",
    num_periods: "",
  });
});
