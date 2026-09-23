/**
 * Hydrate all line-item tables declared via the {% table %} Jinja tag.
 */

import { postJson } from "../api_client.js";
import { renderLineItemPeriodsTable } from "./table_view.js";
import { TableModel } from "./table_model.js";

/** @type {Map<string, TableModel>} tableId -> model, for later lookup (e.g. at submit time). */
const tableModels = new Map();

document
  .querySelectorAll('script[type="application/json"][data-line-item-table]')
  .forEach((dataEl) => {
    const tableId =
      dataEl.dataset.tableId || dataEl.id.replace(/-data$/, "");
    const tableData = JSON.parse(dataEl.textContent);
    const model = TableModel.fromSerialized(tableData);
    tableModels.set(tableId, model);
    model.subscribe((rowId, colId, value) => {
      const input = document.getElementById(`input-${colId}-${rowId}`);
      if (!input) {
        return;
      }
      if (input.type === "checkbox") {
        input.checked = Boolean(value);
      } else {
        input.value = value == null ? "" : value;
      }
    });
    renderLineItemPeriodsTable(tableId, model, { model });
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
