import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";

import { ActionButton } from "../../src/static/js/components/action_button.js";
import { DialogController } from "../../src/static/js/components/dialog_controller.js";
import { FormController } from "../../src/static/js/components/form_controller.js";
import { GenericInput } from "../../src/static/js/components/generic_input.js";
import { closeDom, installDom, settle } from "./dom.js";

let win;
beforeEach(() => {
  win = installDom(`
    <dialog id="dlg"></dialog>
    <button id="btn" type="button">Go</button>
    <form id="form"><input name="a"><button type="submit">Apply</button></form>
    <span id="slot"></span>`);
});
afterEach(() => closeDom(win));

const byId = (id) => document.getElementById(id);

test("GenericInput builds a select with its options and attributes", () => {
  const input = new GenericInput("setting-period", byId("slot"), "quarterly", "select", {
    choices: [
      { value: "annual", label: "Annual" },
      { value: "quarterly", label: "Quarterly" },
    ],
    attributes: { disabled: true, "aria-describedby": null, hidden: false, min: 1, max: 40 },
  });
  const select = byId("setting-period");
  assert.equal(select.tagName, "SELECT");
  assert.deepEqual(
    [...select.options].map((o) => [o.value, o.textContent]),
    [
      ["annual", "Annual"],
      ["quarterly", "Quarterly"],
    ],
  );
  assert.equal(select.value, "quarterly");
  assert.equal(input.get(), "quarterly");
  assert.equal(select.getAttribute("disabled"), "");
  assert.equal(select.getAttribute("min"), "1");
  assert.equal(select.getAttribute("max"), "40");
  assert.equal(select.hasAttribute("aria-describedby"), false);
  assert.equal(select.hasAttribute("hidden"), false);
});

test("GenericInput select reports a user change once and set() writes back", () => {
  const input = new GenericInput("s", byId("slot"), "annual", "select", {
    choices: [
      { value: "annual", label: "Annual" },
      { value: "quarterly", label: "Quarterly" },
    ],
  });
  const select = byId("s");
  const seen = [];
  input.subscribe((value) => seen.push(value));
  select.value = "quarterly";
  select.dispatchEvent(new win.Event("input"));
  select.dispatchEvent(new win.Event("change"));
  assert.deepEqual(seen, ["quarterly"]);
  input.set("annual");
  assert.equal(select.value, "annual");
});

test("DialogController opens and closes, and echoes every close", async () => {
  const dialog = byId("dlg");
  const ctl = new DialogController(dialog);
  const seen = [];
  ctl.subscribe((open) => seen.push(open));
  ctl.set(true);
  assert.equal(dialog.open, true);
  ctl.set(true);
  // Esc, a close button or form method="dialog" all end in dialog.close().
  dialog.close();
  await settle();
  assert.equal(dialog.open, false);
  assert.deepEqual(seen, [false]);
  ctl.set(true);
  ctl.set(false);
  await settle();
  assert.equal(dialog.open, false);
  assert.deepEqual(seen, [false, false]);
});

test("ActionButton reports clicks and writes disabled and aria-expanded", () => {
  const button = byId("btn");
  const ctl = new ActionButton(button);
  let clicks = 0;
  ctl.subscribe(() => clicks++);
  button.click();
  assert.equal(clicks, 1);
  ctl.setDisabled(true);
  assert.equal(button.disabled, true);
  button.click();
  assert.equal(clicks, 1);
  ctl.setDisabled(false);
  ctl.setExpanded(true);
  assert.equal(button.getAttribute("aria-expanded"), "true");
  ctl.setExpanded(false);
  assert.equal(button.getAttribute("aria-expanded"), "false");
});

test("FormController cancels the submit and notifies", () => {
  const form = byId("form");
  const ctl = new FormController(form);
  let submits = 0;
  ctl.subscribe(() => submits++);
  const event = new win.Event("submit", { cancelable: true });
  form.dispatchEvent(event);
  assert.equal(event.defaultPrevented, true);
  form.requestSubmit();
  assert.equal(submits, 2);
});
