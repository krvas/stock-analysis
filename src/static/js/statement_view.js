import {
  renderLineItemFundFlowTable,
  renderLineItemPeriodsTable,
  staticPeriodColumnIds,
} from "./components/table_view.js";

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

const STATEMENT_LABELS = {
  income: "Income Statement",
  balance: "Balance Sheet",
  cashflow: "Cash Flow Statement",
};

const STATEMENT_TABLE_ID = "statement-table";

function getCurrentView() {
  const statementViews = APP_DATA.statements[currentStatementType];
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

  if (
    currentStatementType === "balance" &&
    displayMode === "fund-flow" &&
    periodIds.length > 1 &&
    comparePeriod
  ) {
    renderLineItemFundFlowTable(
      STATEMENT_TABLE_ID,
      view,
      periodIds[0],
      comparePeriod,
    );
    return;
  }

  renderLineItemPeriodsTable(STATEMENT_TABLE_ID, view);
}

function handleStatementTypeChange(statementType) {
  if (!APP_DATA.statements[statementType]) {
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
