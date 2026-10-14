/**
 * Settings drawer and gear hydration and wiring.
 *
 * 1. Read the JSON embedded by `shared/_settings_drawer.html`.
 * 2. DrawerModel.fromSerialized is the source of truth: open flag and field values.
 * 3. render_drawer paints the <dialog>. Field inputs are empty slots.
 * 4. Each slot gets a GenericInput; each button an ActionButton; the <dialog> a
 *    DialogController. Those are the only objects that listen to the DOM.
 * 5. Controllers report into the model; model.subscribe writes back to them.
 * 6. A changed instant field, or Apply, posts model.serialize() to the form
 *    action and reloads `next_path`, which the server renders from the cookie.
 */

import { postForm } from "./api_client.js";
import { ActionButton } from "./components/action_button.js";
import { DialogController } from "./components/dialog_controller.js";
import { DrawerModel } from "./components/drawer_model.js";
import {
  fieldInputId,
  fieldReasonId,
  render_drawer,
} from "./components/drawer_view.js";
import { GenericInput } from "./components/generic_input.js";

function inputFor(field, slot, value) {
  const disabled = field.disabled_reason != null;
  const attributes = {
    disabled,
    "aria-describedby": disabled ? fieldReasonId(field.id) : null,
  };
  if (field.widget === "select") {
    return new GenericInput(fieldInputId(field.id), slot, value, "select", {
      choices: field.options,
      attributes,
    });
  }
  return new GenericInput(fieldInputId(field.id), slot, value, "number", {
    attributes: { ...attributes, min: field.min, max: field.max, step: 1 },
  });
}

async function submit(action, model, instant) {
  await postForm(action, model.serialize({ instant }));
  window.location.assign(model.next_path);
}

function main() {
  const dataEl = document.getElementById("settings-drawer-data");
  const dialog = document.getElementById("settings-drawer");
  if (!dataEl || !dialog) {
    return;
  }
  const action = dataEl.dataset.action;
  const model = DrawerModel.fromSerialized(JSON.parse(dataEl.textContent));
  render_drawer(dialog, model);

  const dialogCtl = new DialogController(dialog);
  dialogCtl.subscribe((open) => model.setOpen(open));

  document
    .querySelectorAll(`[data-settings-open][aria-controls="${dialog.id}"]`)
    .forEach((button) => {
      new ActionButton(button).subscribe(() => model.setOpen(true));
    });
  new ActionButton(dialog.querySelector("[data-drawer-close]")).subscribe(() =>
    model.setOpen(false),
  );
  new ActionButton(dialog.querySelector("[data-drawer-apply]")).subscribe(() =>
    submit(action, model, false),
  );

  /** @type {Map<string, GenericInput>} */
  const inputs = new Map();
  dialog.querySelectorAll("[data-input-slot]").forEach((slot) => {
    const id = slot.dataset.fieldId;
    const input = inputFor(model.field(id), slot, model.getValue(id));
    inputs.set(id, input);
    input.subscribe((value) => model.setValue(id, value));
  });

  model.subscribe((change) => {
    if (change.type === "open") {
      dialogCtl.set(change.open);
      return;
    }
    inputs.get(change.id).set(change.value);
    if (model.field(change.id).instant) {
      submit(action, model, true);
    }
  });

  dialogCtl.set(model.isOpen());
}

main();
