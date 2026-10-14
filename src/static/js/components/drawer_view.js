/**
 * Paints a field drawer into its <dialog>. Field inputs are empty slots
 * (`data-input-slot`, `data-field-id`); buttons are painted bare. No listeners.
 */

const SECTIONS = [
  { key: "global_fields", title: "Global", id: "settings-global-title" },
  { key: "page_fields", title: "This page", id: "settings-page-title" },
];

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

export function fieldInputId(fieldId) {
  return `setting-${fieldId}`;
}

export function fieldReasonId(fieldId) {
  return `${fieldInputId(fieldId)}-reason`;
}

function renderField(field) {
  const row = el("div", {
    class: field.disabled_reason ? "settings-field is-disabled" : "settings-field",
  });
  row.append(
    el("label", { for: fieldInputId(field.id) }, field.label),
    el("span", { "data-input-slot": "", "data-field-id": field.id }),
  );
  if (field.disabled_reason) {
    row.append(
      el(
        "span",
        { class: "settings-reason", id: fieldReasonId(field.id) },
        field.disabled_reason,
      ),
    );
  }
  return row;
}

/**
 * @param {HTMLDialogElement} container
 * @param {import("./drawer_model.js").DrawerModel} drawer
 */
export function render_drawer(container, drawer) {
  container.replaceChildren();

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
  container.append(header);

  if (drawer.error) {
    container.append(
      el("p", { class: "settings-error", role: "alert" }, drawer.error),
    );
  }

  for (const section of SECTIONS) {
    const fields = drawer[section.key];
    if (!fields.length) {
      continue;
    }
    const node = el("section", {
      class: "settings-section",
      "aria-labelledby": section.id,
    });
    node.append(el("h3", { id: section.id }, section.title));
    fields.forEach((field) => node.append(renderField(field)));
    container.append(node);
  }

  const actions = el("div", { class: "settings-actions" });
  actions.append(
    el("button", { type: "button", "data-drawer-apply": "" }, "Apply"),
  );
  container.append(actions);
}
