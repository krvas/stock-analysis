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

function record(model) {
  const changes = [];
  model.subscribe((change) => changes.push(change));
  return changes;
}

test("exposes sections, fields, next path and error", () => {
  const model = drawer({ error: "Invalid view" });
  assert.deepEqual(model.sections(), ["global", "page"]);
  assert.deepEqual(
    model.fields("global").map((f) => f.id),
    ["period", "num_periods", "view"],
  );
  assert.deepEqual(
    model.fields("page").map((f) => f.id),
    ["basis"],
  );
  assert.equal(model.field("view").instant, true);
  assert.equal("value" in model.field("view"), false);
  assert.equal(model.nextPath(), "/statements/AAPL/income");
  assert.equal(model.error(), "Invalid view");
  assert.equal(drawer().error(), null);
});

test("isDisabled and reason follow the server's disabled_reason", () => {
  const model = drawer({
    page_fields: [field("basis", { disabled_reason: "Reported only" })],
  });
  assert.equal(model.isDisabled("basis"), true);
  assert.equal(model.reason("basis"), "Reported only");
  assert.equal(model.isDisabled("period"), false);
  assert.equal(model.reason("period"), null);
});

test("values are normalized per widget so equal values never notify", () => {
  const model = drawer();
  const changes = record(model);
  assert.equal(model.getValue("num_periods"), 10);
  model.setValue("num_periods", 10);
  model.setValue("num_periods", "10");
  model.setValue("period", "annual");
  assert.deepEqual(changes, []);
  model.setValue("period", "quarterly");
  model.setValue("period", "annual");
  model.setValue("period", "annual");
  assert.deepEqual(changes, [
    { type: "value", id: "period", value: "quarterly" },
    { type: "value", id: "period", value: "annual" },
  ]);
});

test("startSave claims one save and clears the previous error", () => {
  const model = drawer({ error: "Invalid view" });
  const changes = record(model);
  assert.equal(model.isSaving(), false);
  assert.equal(model.startSave(), true);
  assert.equal(model.isSaving(), true);
  assert.equal(model.error(), null);
  assert.equal(model.startSave(), false);
  assert.deepEqual(changes, [
    { type: "saving", saving: true },
    { type: "error", error: null },
  ]);
});

test("failSave ends the save and records the error", () => {
  const model = drawer();
  model.startSave();
  const changes = record(model);
  model.failSave("Settings were not saved: boom");
  assert.equal(model.isSaving(), false);
  assert.equal(model.error(), "Settings were not saved: boom");
  assert.deepEqual(changes, [
    { type: "saving", saving: false },
    { type: "error", error: "Settings were not saved: boom" },
  ]);
  assert.equal(model.startSave(), true);
});

test("serialize reflects edits made after a failed save", () => {
  const model = drawer();
  model.startSave();
  model.failSave("nope");
  model.setValue("period", "quarterly");
  assert.equal(model.serialize({ instant: false }).period, "quarterly");
  assert.deepEqual(model.serialize({ instant: true }), {
    next: "/statements/AAPL/income",
    view: "standard",
  });
});
