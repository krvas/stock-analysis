/**
 * Hydrate all line-item tables declared via the {% table %} Jinja tag.
 */

import { renderLineItemPeriodsTable } from "./tables.js";

document
  .querySelectorAll('script[type="application/json"][data-line-item-table]')
  .forEach((dataEl) => {
    const tableId =
      dataEl.dataset.tableId || dataEl.id.replace(/-data$/, "");
    const { rows, periods } = JSON.parse(dataEl.textContent);
    renderLineItemPeriodsTable(tableId, rows, periods);
  });
