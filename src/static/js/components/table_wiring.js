/**
 * Wizard line-item table hydration and save wiring.
 *
 * 1. Read the JSON embedded by the {% table %} tag.
 * 2. TableModel.fromSerialized is the source of truth.
 * 3. render_table paints headers, labels, static cells, and link cells. Input columns are empty slots.
 * 4. Each slot gets a GenericInput. That class is the only place that listens to the input element.
 * 5. input.subscribe sends the coerced value to model.setCell.
 * 6. model.subscribe writes linked-group updates back with input.set. GenericInput ignores a set that does not change the value, so this does not loop.
 * 7. Save posts model.serialize(), which includes input columns only.
 */

import { postJson } from "../api_client.js";
import { GenericInput } from "./generic_input.js";
import { render_table } from "./table_view.js";
import { TableModel } from "./table_model.js";

/** @type {Map<string, TableModel>} tableId -> model, for later lookup (e.g. at submit time). */
const tableModels = new Map();

function htmlInputType(dtype) {
  if (dtype === "boolean") {
    return "checkbox";
  }
  if (dtype === "number") {
    return "number";
  }
  return "text";
}

/**
 * @param {TableModel} model
 * @param {HTMLTableElement} container
 */
function wireTableInputs(model, container) {
  /** @type {Map<string, GenericInput>} */
  const inputsByCell = new Map();

  container.querySelectorAll("[data-input-slot]").forEach((slot) => {
    const rowId = slot.dataset.rowId;
    const colId = slot.dataset.colId;
    const dtype = slot.dataset.dtype;
    const type = htmlInputType(dtype);
    const input = new GenericInput(
      `input-${colId}-${rowId}`,
      slot,
      model.getCell(rowId, colId),
      type,
    );
    inputsByCell.set(`${rowId}\0${colId}`, input);
    input.subscribe((value) => model.setCell(rowId, colId, value));
  });

  model.subscribe((rowId, colId, value) => {
    const input = inputsByCell.get(`${rowId}\0${colId}`);
    if (input) {
      input.set(value);
    }
  });
}

document
  .querySelectorAll('script[type="application/json"][data-line-item-table]')
  .forEach((dataEl) => {
    const tableId =
      dataEl.dataset.tableId || dataEl.id.replace(/-data$/, "");
    const tableData = JSON.parse(dataEl.textContent);
    const model = TableModel.fromSerialized(tableData);
    tableModels.set(tableId, model);

    const container = document.getElementById(tableId);
    render_table(container, model);
    wireTableInputs(model, container);
  });

/**
 * Generic wizard save-body builder: {exchange, columns, rows}, where
 * {columns, rows} is exactly what TableModel.serialize() returns (only the
 * input columns and their values). No subpage-specific field knowledge
 * belongs here — that lives in the backend route builder for the subpage
 * in question.
 */
function buildWizardSaveBody(form) {
  const exchange = form.dataset.exchange;
  if (!exchange || !String(exchange).trim()) {
    throw new Error("Missing data-exchange on form");
  }
  const tableId = form.dataset.tableId;
  if (!tableId) {
    throw new Error("Missing data-table-id on form");
  }
  const model = tableModels.get(tableId);
  if (!model) {
    throw new Error(`Table model not found: ${tableId}`);
  }

  return {
    exchange: String(exchange).trim(),
    ...model.serialize(),
  };
}

function bindWizardSaveForms() {
  document.querySelectorAll("form[data-wizard-save]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();

      let body;
      try {
        body = buildWizardSaveBody(form);
      } catch (err) {
        alert(err instanceof Error ? err.message : String(err));
        return;
      }

      const submitButton = form.querySelector('button[type="submit"]');
      if (submitButton) {
        submitButton.disabled = true;
      }

      try {
        await postJson(form.action, body);
        window.location.reload();
      } catch (err) {
        alert(err instanceof Error ? err.message : String(err));
      } finally {
        if (submitButton) {
          submitButton.disabled = false;
        }
      }
    });
  });
}

bindWizardSaveForms();
