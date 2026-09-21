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

function appendValueCells(tr, values, unitKey) {
  const currentUnit = unitKey || getStatementUnit();
  values.forEach((value) => {
    const valueCell = document.createElement("td");
    valueCell.innerHTML = formatNumber(value, currentUnit);
    tr.appendChild(valueCell);
  });
}

/**
 * Render rows with one column per period (standard statement layout).
 *
 * @param {string} tableId - Element id of a table with thead/tbody
 * @param {Array<{ label, level, is_total, values: Record<string, number|null> }>} rows
 * @param {string[]} periods - Column keys matching row.values
 * @param {{ unitKey?: string }} [options]
 */
export function renderLineItemPeriodsTable(tableId, rows, periods, options = {}) {
  const { thead, tbody } = getTableParts(tableId);
  clearTable(thead, tbody);

  const unitLabel = getUnitLabel(options.unitKey);
  thead.appendChild(
    buildHeaderRow(periods, `Line Item (in ${unitLabel})`),
  );

  rows.forEach((row) => {
    const tr = document.createElement("tr");
    appendLineItemLabelCell(tr, row);
    appendValueCells(
      tr,
      periods.map((period) => row.values[period]),
      options.unitKey,
    );
    tbody.appendChild(tr);
  });
}

/**
 * Render fund-flow layout: latest period, compare period, and change column.
 */
export function renderLineItemFundFlowTable(
  tableId,
  rows,
  latestPeriod,
  previousPeriod,
  options = {},
) {
  const { thead, tbody } = getTableParts(tableId);
  clearTable(thead, tbody);

  const unitLabel = getUnitLabel(options.unitKey);
  const columnLabels = [latestPeriod, previousPeriod, "Change"];
  thead.appendChild(
    buildHeaderRow(columnLabels, `Line Item (in ${unitLabel})`),
  );

  rows.forEach((row) => {
    const tr = document.createElement("tr");
    appendLineItemLabelCell(tr, row);

    const latestValue = row.values[latestPeriod];
    const previousValue = row.values[previousPeriod];
    const difference = computeDifference(latestValue, previousValue);
    appendValueCells(
      tr,
      [latestValue, previousValue, difference],
      options.unitKey,
    );

    tbody.appendChild(tr);
  });
}
