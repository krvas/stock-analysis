import { render_table } from "./components/table_view.js";
import { computeDifference } from "./utils.js";

function staticPeriodColumnIds(columns) {
  return columns
    .filter((col) => col.kind === "static" && col.dtype === "number")
    .map((col) => col.id);
}

const dataEl = document.getElementById("statement-data");
if (!dataEl) {
  // Not on the statements page; nothing to initialize.
} else {
  runStatementView(JSON.parse(dataEl.textContent));
}

function runStatementView(APP_DATA) {

let currentStatementType = "income";
let displayMode = "periods";
let comparePeriod = null;
const hasAdjusted = Boolean(APP_DATA.adjusted_statements);
let currentBasis =
  hasAdjusted &&
  new URLSearchParams(window.location.search).get("basis") === "adjusted"
    ? "adjusted"
    : "reported";

const STATEMENT_LABELS = {
  income: "Income Statement",
  balance: "Balance Sheet",
  cashflow: "Cash Flow Statement",
};

const STATEMENT_TABLE_ID = "statement-table";

function activeStatements() {
  return currentBasis === "adjusted"
    ? APP_DATA.adjusted_statements
    : APP_DATA.statements;
}

function getCurrentView() {
  const statementViews = activeStatements()[currentStatementType];
  if (!statementViews) {
    return null;
  }
  const viewName = document.getElementById("view-select").value;
  return statementViews[viewName];
}

function updateComparePeriodOptions(periodIds) {
  const select = document.getElementById("compare-period-select");
  const previousPeriods = periodIds.slice(1);

  select.innerHTML = "";
  previousPeriods.forEach((period) => {
    const option = document.createElement("option");
    option.value = period;
    option.textContent = period;
    select.appendChild(option);
  });

  if (previousPeriods.length === 0) {
    comparePeriod = null;
    return;
  }

  if (!comparePeriod || !previousPeriods.includes(comparePeriod)) {
    comparePeriod = previousPeriods[0];
  }
  select.value = comparePeriod;
}

function updateControlVisibility() {
  const isBalanceSheet = currentStatementType === "balance";
  const fundFlowControls = document.getElementById("fund-flow-controls");
  const compareControls = document.getElementById("compare-period-controls");
  const displayModeSelect = document.getElementById("display-mode-select");

  fundFlowControls.hidden = !isBalanceSheet;

  if (!isBalanceSheet) {
    displayMode = "periods";
    displayModeSelect.value = "periods";
    compareControls.hidden = true;
    return;
  }

  compareControls.hidden = displayMode !== "fund-flow";
}

function updatePageTitle() {
  const statementLabel =
    STATEMENT_LABELS[currentStatementType] || currentStatementType;
  const periodLabel = APP_DATA.period === "quarterly" ? "Quarterly" : "Annual";

  document.getElementById("page-title").textContent =
    `${APP_DATA.ticker} — ${statementLabel}`;
  document.getElementById("page-subtitle").textContent =
    `${periodLabel} · SEC EDGAR via edgartools`;
}

function handleViewChange() {
  const view = getCurrentView();
  if (!view) {
    return;
  }

  const periodIds = staticPeriodColumnIds(view.columns);
  updateComparePeriodOptions(periodIds);
  updateControlVisibility();

  const tableEl = document.getElementById(STATEMENT_TABLE_ID);

  if (
    currentStatementType === "balance" &&
    displayMode === "fund-flow" &&
    periodIds.length > 1 &&
    comparePeriod
  ) {
    const latestPeriodId = periodIds[0];
    const previousPeriodId = comparePeriod;
    render_table(tableEl, {
      columns: [
        {
          id: latestPeriodId,
          label: latestPeriodId,
          kind: "static",
          dtype: "number",
        },
        {
          id: previousPeriodId,
          label: previousPeriodId,
          kind: "static",
          dtype: "number",
        },
        {
          id: "change",
          label: "Change",
          kind: "static",
          dtype: "number",
        },
      ],
      rows: view.rows.map((row) => ({
        id: row.id,
        label: row.label,
        level: row.level,
        is_total: row.is_total,
        origin: row.origin,
        cells: {
          ...row.cells,
          change: computeDifference(
            row.cells[latestPeriodId],
            row.cells[previousPeriodId],
          ),
        },
      })),
    });
    return;
  }

  render_table(tableEl, view);
}

function updateBasisControls() {
  const basisControls = document.getElementById("basis-controls");
  const note = document.getElementById("adjustments-note");
  basisControls.hidden = !hasAdjusted;
  basisControls.querySelectorAll("button[data-basis]").forEach((button) => {
    button.setAttribute(
      "aria-pressed",
      String(button.dataset.basis === currentBasis),
    );
  });

  const labels = (APP_DATA.adjustments || []).map((adj) => adj.label);
  note.hidden = currentBasis !== "adjusted";
  note.textContent = labels.length
    ? `Adjusted for: ${labels.join(" · ")}`
    : "Adjusted basis (no adjustments applied)";
}

function handleBasisChange(basis) {
  if (basis === currentBasis || (basis === "adjusted" && !hasAdjusted)) {
    return;
  }
  currentBasis = basis;
  updateBasisControls();
  handleViewChange();
}

function handleStatementTypeChange(statementType) {
  if (!activeStatements()[statementType]) {
    return;
  }
  currentStatementType = statementType;
  updatePageTitle();
  handleViewChange();
}

function handleDisplayModeChange(mode) {
  displayMode = mode;
  updateControlVisibility();
  handleViewChange();
}

function handleComparePeriodChange(period) {
  comparePeriod = period;
  handleViewChange();
}

function initPage() {
  updatePageTitle();
  updateBasisControls();

  document
    .querySelectorAll("#basis-controls button[data-basis]")
    .forEach((button) => {
      button.addEventListener("click", () => {
        handleBasisChange(button.dataset.basis);
      });
    });

  const viewSelect = document.getElementById("view-select");
  viewSelect.addEventListener("change", handleViewChange);

  const statementTypeSelect = document.getElementById("statement-type-select");
  statementTypeSelect.addEventListener("change", (event) => {
    handleStatementTypeChange(event.target.value);
  });

  const displayModeSelect = document.getElementById("display-mode-select");
  displayModeSelect.addEventListener("change", (event) => {
    handleDisplayModeChange(event.target.value);
  });

  const comparePeriodSelect = document.getElementById("compare-period-select");
  comparePeriodSelect.addEventListener("change", (event) => {
    handleComparePeriodChange(event.target.value);
  });

  handleViewChange();
}

  initPage();
}
