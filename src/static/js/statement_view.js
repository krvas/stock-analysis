(() => {
  const dataEl = document.getElementById("statement-data");
  if (!dataEl) {
    return;
  }

  const APP_DATA = JSON.parse(dataEl.textContent);

  let currentStatementType = "income";
  let displayMode = "periods";
  let comparePeriod = null;

  const STATEMENT_LABELS = {
    income: "Income Statement",
    balance: "Balance Sheet",
    cashflow: "Cash Flow Statement",
  };

  const UNIT_OPTIONS = {
    billions: { scale: 1e9, label: 'billions' },
    millions: { scale: 1e6, label: 'millions' },
    thousands: { scale: 1e3, label: 'thousands' },
    units: { scale: 1, label: 'units' },
  };
  // runtime-selected unit; replaceable by future feature
  let CURRENT_UNIT = 'millions';

  // Expose simple runtime getters/setters so a future UI or server
  // integration can call `window.setStatementUnit('billions')`.
  window.getStatementUnit = function () {
    return window.STATEMENT_UNIT || CURRENT_UNIT;
  };
  window.setStatementUnit = function (key) {
    if (UNIT_OPTIONS[key]) {
      CURRENT_UNIT = key;
      window.STATEMENT_UNIT = key;
    }
  };

  function formatNumber(value, unitKey) {
    if (value === null || value === undefined) {
      return '<span class="empty">—</span>';
    }
    const unit = UNIT_OPTIONS[unitKey] || UNIT_OPTIONS.millions;
    const scaled = value / unit.scale;
    return scaled.toLocaleString(undefined, { maximumFractionDigits: 0 });
  }

  function computeDifference(latest, previous) {
    if (
      latest === null || latest === undefined ||
      previous === null || previous === undefined
    ) {
      return null;
    }
    return latest - previous;
  }

  function renderTable(rows, periods) {
    const table = document.getElementById("statement-table");
    const thead = table.querySelector("thead");
    const tbody = table.querySelector("tbody");

    thead.innerHTML = "";
    tbody.innerHTML = "";

    const headerRow = document.createElement("tr");
    const labelHeader = document.createElement("th");
    const currentUnit = window.getStatementUnit();
    const unitLabel = UNIT_OPTIONS[currentUnit].label;
    labelHeader.textContent = `Line Item (in ${unitLabel})`;
    headerRow.appendChild(labelHeader);

    periods.forEach((period) => {
      const th = document.createElement("th");
      th.textContent = period;
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

      periods.forEach((period) => {
        const valueCell = document.createElement("td");
        valueCell.innerHTML = formatNumber(row.values[period], currentUnit);
        tr.appendChild(valueCell);
      });

      tbody.appendChild(tr);
    });
  }

  function renderFundFlowTable(rows, latestPeriod, previousPeriod) {
    const table = document.getElementById("statement-table");
    const thead = table.querySelector("thead");
    const tbody = table.querySelector("tbody");

    thead.innerHTML = "";
    tbody.innerHTML = "";

    const headerRow = document.createElement("tr");
    const labelHeader = document.createElement("th");
    const currentUnit = window.getStatementUnit();
    const unitLabel = UNIT_OPTIONS[currentUnit].label;
    labelHeader.textContent = `Line Item (in ${unitLabel})`;
    headerRow.appendChild(labelHeader);

    [latestPeriod, previousPeriod, "Change"].forEach((label) => {
      const th = document.createElement("th");
      th.textContent = label;
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

      const latestValue = row.values[latestPeriod];
      const previousValue = row.values[previousPeriod];
      const difference = computeDifference(latestValue, previousValue);

      [latestValue, previousValue, difference].forEach((value) => {
        const valueCell = document.createElement("td");
        valueCell.innerHTML = formatNumber(value, currentUnit);
        tr.appendChild(valueCell);
      });

      tbody.appendChild(tr);
    });
  }

  function getCurrentView() {
    const statementViews = APP_DATA.statements[currentStatementType];
    if (!statementViews) {
      return null;
    }
    const viewName = document.getElementById("view-select").value;
    return statementViews[viewName];
  }

  function updateComparePeriodOptions(periods) {
    const select = document.getElementById("compare-period-select");
    const previousPeriods = periods.slice(1);

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

    updateComparePeriodOptions(view.periods);
    updateControlVisibility();

    if (
      currentStatementType === "balance" &&
      displayMode === "fund-flow" &&
      view.periods.length > 1 &&
      comparePeriod
    ) {
      renderFundFlowTable(view.rows, view.periods[0], comparePeriod);
      return;
    }

    renderTable(view.rows, view.periods);
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
})();
