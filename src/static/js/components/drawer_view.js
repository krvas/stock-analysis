/**
 * Paints a field drawer into its <dialog> and owns the per-field control
 * spec. Fields sit in a <form> (`data-drawer-form`) so Enter submits; field
 * inputs are empty slots (`data-input-slot`, `data-field-id`); buttons are
 * painted bare. No listeners.
 */

const SECTIONS = {
  global: { title: "Global", id: "settings-global-title" },
  page: { title: "This page", id: "settings-page-title" },
};

function el(tag, attrs = {}, text) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    node.setAttribute(name, value);
  }
  if (text != null) {
    node.textContent = text;
  }
  return node;
}

function fieldInputId(fieldId) {
  return `setting-${fieldId}`;
}

function fieldReasonId(fieldId) {
  return `${fieldInputId(fieldId)}-reason`;
}

/**
 * How to build the control in a field's slot: the `GenericInput` id, type
 * and options.
 *
 * @param {import("./drawer_model.js").DrawerModel} drawer
 * @param {string} id
 * @returns {{id: string, type: "select" | "number", options: object}}
 */
export function controlSpec(drawer, id) {
  const field = drawer.field(id);
  const disabled = drawer.isDisabled(id);
  const attributes = {
    disabled,
    "aria-describedby": disabled ? fieldReasonId(id) : null,
  };
  if (field.widget === "select") {
    return {
      id: fieldInputId(id),
      type: "select",
      options: { choices: field.options, attributes },
    };
  }
  return {
    id: fieldInputId(id),
    type: "number",
    options: {
      attributes: { ...attributes, min: field.min, max: field.max, step: 1 },
    },
  };
}

function renderField(drawer, field) {
  const reason = drawer.reason(field.id);
  const row = el("div", {
    class: reason ? "settings-field is-disabled" : "settings-field",
  });
  row.append(
    el("label", { for: fieldInputId(field.id) }, field.label),
    el("span", { "data-input-slot": "", "data-field-id": field.id }),
  );
  if (reason) {
    row.append(
      el("span", { class: "settings-reason", id: fieldReasonId(field.id) }, reason),
    );
  }
  return row;
}

function renderHeader(container) {
  const header = el("div", { class: "settings-drawer-header" });
  header.append(
    el("h2", { id: container.getAttribute("aria-labelledby") }, "Settings"),
    el(
      "button",
      {
        type: "button",
        class: "settings-close",
        "aria-label": "Close settings",
        "data-drawer-close": "",
      },
      "×",
    ),
  );
  return header;
}

/**
 * Shows `message` in the drawer's alert, or hides the alert when null.
 *
 * @param {HTMLDialogElement} container
 * @param {string | null} message
 */
export function paint_error(container, message) {
  const alert = container.querySelector("[data-drawer-error]");
  alert.textContent = message ?? "";
  alert.hidden = message == null;
}

/**
 * Paints a drawer with only its header and `message`, for when the drawer
 * data cannot be read.
 *
 * @param {HTMLDialogElement} container
 * @param {string} message
 */
export function render_unavailable(container, message) {
  container.replaceChildren(
    renderHeader(container),
    el("p", { class: "settings-error", role: "alert" }, message),
  );
}

/**
 * @param {HTMLDialogElement} container
 * @param {import("./drawer_model.js").DrawerModel} drawer
 */
export function render_drawer(container, drawer) {
  const form = el("form", { "data-drawer-form": "" });
  form.append(
    el("p", { class: "settings-error", role: "alert", "data-drawer-error": "" }),
  );

  for (const sectionKey of drawer.sections()) {
    const fields = drawer.fields(sectionKey);
    if (!fields.length) {
      continue;
    }
    const section = SECTIONS[sectionKey];
    const node = el("section", {
      class: "settings-section",
      "aria-labelledby": section.id,
    });
    node.append(el("h3", { id: section.id }, section.title));
    fields.forEach((field) => node.append(renderField(drawer, field)));
    form.append(node);
  }

  const actions = el("div", { class: "settings-actions" });
  actions.append(
    el("button", { type: "submit", "data-drawer-apply": "" }, "Apply"),
  );
  form.append(actions);

  container.replaceChildren(renderHeader(container), form);
  paint_error(container, drawer.error());
}
