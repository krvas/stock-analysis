(() => {
  const dataEl = document.getElementById("statement-data");
  if (!dataEl) {
    return;
  }

  const APP_DATA = JSON.parse(dataEl.textContent);

  const STATEMENT_LABELS = {
    income: "Income Statement",
    balance: "Balance Sheet",
    cashflow: "Cash Flow Statement",
  };

  function formatNumber(value) {
    if (value === null || value === undefined) {
      return '<span class="empty">—</span>';
    }
    const abs = Math.abs(value);
    let formatted;
    if (abs >= 1e9) {
      formatted = (value / 1e9).toFixed(2) + "B";
    } else if (abs >= 1e6) {
      formatted = (value / 1e6).toFixed(2) + "M";
    } else if (abs >= 1e3) {
      formatted = (value / 1e3).toFixed(2) + "K";
    } else {
      formatted = value.toLocaleString(undefined, { maximumFractionDigits: 2 });
    }
    return formatted;
  }

  function renderTable(rows, periods) {
    const table = document.getElementById("statement-table");
    const thead = table.querySelector("thead");
    const tbody = table.querySelector("tbody");

    thead.innerHTML = "";
    tbody.innerHTML = "";

    const headerRow = document.createElement("tr");
    const labelHeader = document.createElement("th");
    labelHeader.textContent = "Line Item";
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
        valueCell.innerHTML = formatNumber(row.values[period]);
        tr.appendChild(valueCell);
      });

      tbody.appendChild(tr);
    });
  }

  function handleViewChange(viewName) {
    const view = APP_DATA.views[viewName];
    if (!view) {
      return;
    }
    renderTable(view.rows, view.periods);
  }

  function initPage() {
    const statementLabel = STATEMENT_LABELS[APP_DATA.statement_type] || APP_DATA.statement_type;
    const periodLabel = APP_DATA.period === "quarterly" ? "Quarterly" : "Annual";

    document.getElementById("page-title").textContent =
      `${APP_DATA.ticker} — ${statementLabel}`;
    document.getElementById("page-subtitle").textContent =
      `${periodLabel} · SEC EDGAR via edgartools`;

    const select = document.getElementById("view-select");
    select.addEventListener("change", (event) => {
      handleViewChange(event.target.value);
    });

    handleViewChange(select.value);
  }

  initPage();
})();
