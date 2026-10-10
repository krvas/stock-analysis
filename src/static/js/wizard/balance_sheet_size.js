// Business Understanding › Balance Sheet Size: two treemaps from embedded Table JSON.
import { render_treemap } from "../components/treemap_view.js";

const EQUITY_ROW_ID = "equity";

// TODO: units should become user-selectable (a page-level units option); at that
// point use `formatNumber` from utils.js here instead.
function format_billions(value) {
  return `$${(value / 1e9).toFixed(1)}B`;
}

function main() {
  document.querySelectorAll("[data-treemap]").forEach((container) => {
    const table = JSON.parse(document.getElementById(container.dataset.source).textContent);
    render_treemap(container, table, "value", {
      format: format_billions,
      className: (row) =>
        row.id === EQUITY_ROW_ID ? "treemap-equity" : `treemap-${container.dataset.treemap}`,
    });
  });
}

main();
