/**
 * DOM helpers for line-item financial tables (statements, wizard adjustments, etc.).
 */

import {
  computeDifference,
  formatNumber,
  getStatementUnit,
  getUnitLabel,
} from "./utils.js";

function getTableParts(tableId) {
  const table = document.getElementById(tableId);
  if (!table) {
    throw new Error(`Table not found: #${tableId}`);
  }
  const thead = table.querySelector("thead");
  const tbody = table.querySelector("tbody");
  if (!thead || !tbody) {
    throw new Error(`Table #${tableId} must contain thead and tbody`);
  }
  return { thead, tbody };
}

function clearTable(thead, tbody) {
  thead.innerHTML = "";
  tbody.innerHTML = "";
}

function buildHeaderRow(columnLabels, labelHeaderText) {
  const headerRow = document.createElement("tr");
  const labelHeader = document.createElement("th");
  labelHeader.textContent = labelHeaderText;
  headerRow.appendChild(labelHeader);

  columnLabels.forEach((label) => {
    const th = document.createElement("th");
    th.textContent = label;
    headerRow.appendChild(th);
  });

  return headerRow;
}

function appendLineItemLabelCell(tr, row) {
  const labelCell = document.createElement("td");
  const labelSpan = document.createElement("span");
  labelSpan.className = "line-label" + (row.is_total ? " total" : "");
  labelSpan.style.paddingLeft = `${Math.max(row.level, 0) * 16}px`;
  labelSpan.textContent = row.label;
  labelCell.appendChild(labelSpan);
  tr.appendChild(labelCell);
}

function appendStaticValueCell(tr, value, unitKey) {
  const valueCell = document.createElement("td");
  valueCell.innerHTML = formatNumber(value, unitKey || getStatementUnit());
  tr.appendChild(valueCell);
}

function appendInputCell(tr, col, row) {
  const element = document.createElement("input");
  if (col.dtype === "boolean") {
    element.type = "checkbox";
  } else if (col.dtype === "number") {
    element.type = "number";
  } else {
    element.type = "text";
  }
  element.id = `input-${col.id}-${row.id}`;
  const td = document.createElement("td");
  td.appendChild(element);
  tr.appendChild(td);
}

function appendLinkCell(tr, cell) {
  const td = document.createElement("td");
  if (cell && typeof cell === "object" && cell.href) {
    const anchor = document.createElement("a");
    anchor.href = cell.href;
    anchor.textContent = cell.text ?? cell.href;
    td.appendChild(anchor);
  } else {
    td.textContent = "";
  }
  tr.appendChild(td);
}

/**
 * Static period column ids in schema order (excludes input/link columns).
 *
 * @param {Array<{ id, kind, dtype }>} columns
 * @returns {string[]}
 */
export function staticPeriodColumnIds(columns) {
  return columns
    .filter((col) => col.kind === "static" && col.dtype === "number")
    .map((col) => col.id);
}

/**
 * Render a column-schema table (periods, inputs, links).
 *
 * @param {string} tableId - Element id of a table with thead/tbody
 * @param {{ columns: object[], rows: object[] }} tableData
 * @param {{ unitKey?: string }} [options]
 */
export function renderLineItemPeriodsTable(tableId, tableData, options = {}) {
  const { thead, tbody } = getTableParts(tableId);
  clearTable(thead, tbody);

  const { columns, rows } = tableData;
  const unitLabel = getUnitLabel(options.unitKey);
  thead.appendChild(
    buildHeaderRow(
      columns.map((col) => col.label),
      `Line Item (in ${unitLabel})`,
    ),
  );

  rows.forEach((row) => {
    const tr = document.createElement("tr");
    appendLineItemLabelCell(tr, row);

    columns.forEach((col) => {
      const value = row.cells[col.id];
      if (col.kind === "static") {
        appendStaticValueCell(tr, value, options.unitKey);
        return;
      }
      if (col.kind === "input") {
        appendInputCell(tr, col, row);
        return;
      }
      if (col.kind === "link") {
        appendLinkCell(tr, value);
      }
    });

    tbody.appendChild(tr);
  });
}

/**
 * Render fund-flow layout: latest period, compare period, and change column.
 *
 * @param {string} tableId
 * @param {{ columns: object[], rows: object[] }} tableData
 * @param {string} latestPeriodId
 * @param {string} previousPeriodId
 * @param {{ unitKey?: string }} [options]
 */
export function renderLineItemFundFlowTable(
  tableId,
  tableData,
  latestPeriodId,
  previousPeriodId,
  options = {},
) {
  const { thead, tbody } = getTableParts(tableId);
  clearTable(thead, tbody);

  const { rows } = tableData;
  const unitLabel = getUnitLabel(options.unitKey);
  const columnLabels = [latestPeriodId, previousPeriodId, "Change"];
  thead.appendChild(
    buildHeaderRow(columnLabels, `Line Item (in ${unitLabel})`),
  );

  rows.forEach((row) => {
    const tr = document.createElement("tr");
    appendLineItemLabelCell(tr, row);

    const latestValue = row.cells[latestPeriodId];
    const previousValue = row.cells[previousPeriodId];
    const difference = computeDifference(latestValue, previousValue);
    appendStaticValueCell(tr, latestValue, options.unitKey);
    appendStaticValueCell(tr, previousValue, options.unitKey);
    appendStaticValueCell(tr, difference, options.unitKey);

    tbody.appendChild(tr);
  });
}
