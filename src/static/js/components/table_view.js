/**
 * Paints a table object into a container. No event handlers.
 */

import { formatNumber, getStatementUnit, getUnitLabel } from "../utils.js";

/**
 * @param {HTMLTableElement} container - Existing table with thead and tbody
 * @param {{ columns: object[], rows: object[] }} table
 */
export function render_table(container, table) {
  if (!container) {
    throw new Error("Table container is required");
  }
  const thead = container.querySelector("thead");
  const tbody = container.querySelector("tbody");
  if (!thead || !tbody) {
    throw new Error("Table container must contain thead and tbody");
  }

  thead.innerHTML = "";
  tbody.innerHTML = "";

  const { columns, rows } = table;
  const unitLabel = getUnitLabel();
  const headerRow = document.createElement("tr");
  const labelHeader = document.createElement("th");
  labelHeader.textContent = `Line Item (in ${unitLabel})`;
  headerRow.appendChild(labelHeader);
  columns.forEach((col) => {
    const th = document.createElement("th");
    th.textContent = col.label;
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);

  rows.forEach((row) => {
    const tr = document.createElement("tr");

    const labelCell = document.createElement("td");
    const labelSpan = document.createElement("span");
    labelSpan.className = "line-label" + (row.is_total ? " total" : "");
    labelSpan.style.paddingLeft = `${Math.max(row.level, 0) * 16}px`;
    labelSpan.textContent = row.label;
    labelCell.appendChild(labelSpan);
    tr.appendChild(labelCell);

    columns.forEach((col) => {
      const value = row.cells[col.id];
      if (col.kind === "static") {
        const valueCell = document.createElement("td");
        valueCell.innerHTML = formatNumber(value, getStatementUnit());
        tr.appendChild(valueCell);
        return;
      }
      if (col.kind === "link") {
        const td = document.createElement("td");
        if (value && typeof value === "object" && value.href) {
          const anchor = document.createElement("a");
          anchor.href = value.href;
          anchor.textContent = value.text ?? value.href;
          td.appendChild(anchor);
        } else {
          td.textContent = "";
        }
        tr.appendChild(td);
        return;
      }
      if (col.kind === "input") {
        const td = document.createElement("td");
        td.dataset.inputSlot = "";
        td.dataset.rowId = row.id;
        td.dataset.colId = col.id;
        td.dataset.dtype = col.dtype;
        tr.appendChild(td);
      }
    });

    tbody.appendChild(tr);
  });
}
