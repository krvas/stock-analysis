/**
 * Settings drawer and gear hydration and wiring.
 *
 * 1. Read the JSON embedded by `shared/_settings_drawer.html`.
 * 2. DrawerModel.fromSerialized is the source of truth: open flag, field
 *    values, save state and error.
 * 3. render_drawer paints the <dialog>. Field inputs are empty slots.
 * 4. Each slot gets a GenericInput built from controlSpec; each button an
 *    ActionButton; the field <form> a FormController; the <dialog> a
 *    DialogController. Those are the only objects that touch the DOM.
 * 5. Controllers report into the model; model.subscribe writes back to them.
 * 6. A changed instant field, or submitting the form (Apply or Enter), posts
 *    model.serialize() to the form action and reloads `next_path`, which the
 *    server renders from the cookie. One save runs at a time; a failed one
 *    lands in the model's error and the drawer stays open.
 */

import { postForm } from "./api_client.js";
import { ActionButton } from "./components/action_button.js";
import { DialogController } from "./components/dialog_controller.js";
import { DrawerModel } from "./components/drawer_model.js";
import {
  controlSpec,
  paint_error,
  render_drawer,
  render_unavailable,
} from "./components/drawer_view.js";
import { FormController } from "./components/form_controller.js";
import { GenericInput } from "./components/generic_input.js";

const UNAVAILABLE = "Settings could not be loaded. Reload the page to try again.";

async function submit(action, model, instant) {
  if (!model.startSave()) {
    return;
  }
  try {
    await postForm(action, model.serialize({ instant }));
  } catch (error) {
    model.failSave(`Settings were not saved: ${error.message}`);
    return;
  }
  window.location.assign(model.nextPath());
}

function hydrate(dialog, dataEl) {
  try {
    const model = DrawerModel.fromSerialized(JSON.parse(dataEl.textContent));
    render_drawer(dialog, model);
    return model;
  } catch (error) {
    console.error("Settings drawer data is unreadable", error);
    return null;
  }
}

function main() {
  const dialog = document.getElementById("settings-drawer");
  if (!dialog) {
    return;
  }
  const dataEl = document.getElementById("settings-drawer-data");
  const action = dataEl?.dataset.action;
  const loaded = dataEl && action ? hydrate(dialog, dataEl) : null;
  const model =
    loaded ??
    DrawerModel.fromSerialized({
      next_path: window.location.pathname,
      error: null,
      global_fields: [],
      page_fields: [],
    });
  if (!loaded) {
    render_unavailable(dialog, UNAVAILABLE);
  }

  const dialogCtl = new DialogController(dialog);
  dialogCtl.subscribe((open) => model.setOpen(open));

  const gears = [
    ...document.querySelectorAll(
      `[data-settings-open][aria-controls="${dialog.id}"]`,
    ),
  ].map((button) => new ActionButton(button));
  gears.forEach((gear) => gear.subscribe(() => model.setOpen(true)));
  new ActionButton(dialog.querySelector("[data-drawer-close]")).subscribe(() =>
    model.setOpen(false),
  );

  const syncOpen = (open) => {
    dialogCtl.set(open);
    gears.forEach((gear) => gear.setExpanded(open));
  };

  model.subscribe((change) => {
    if (change.type === "open") {
      syncOpen(change.open);
    }
  });
  syncOpen(model.isOpen());
  if (!loaded) {
    return;
  }

  const apply = new ActionButton(dialog.querySelector("[data-drawer-apply]"));
  new FormController(dialog.querySelector("[data-drawer-form]")).subscribe(() =>
    submit(action, model, false),
  );

  /** @type {Map<string, GenericInput>} */
  const inputs = new Map();
  dialog.querySelectorAll("[data-input-slot]").forEach((slot) => {
    const id = slot.dataset.fieldId;
    const spec = controlSpec(model, id);
    const input = new GenericInput(
      spec.id,
      slot,
      model.getValue(id),
      spec.type,
      spec.options,
    );
    inputs.set(id, input);
    input.subscribe((value) => model.setValue(id, value));
  });

  model.subscribe((change) => {
    if (change.type === "saving") {
      apply.setDisabled(change.saving);
    } else if (change.type === "error") {
      paint_error(dialog, change.error);
    } else if (change.type === "value") {
      inputs.get(change.id).set(change.value);
      if (model.field(change.id).instant) {
        submit(action, model, true);
      }
    }
  });
}

main();
