// Business Understanding › Balance Sheet Size: two treemaps from embedded Table JSON.
import { render_treemap } from "../components/treemap_view.js";

const EQUITY_ROW_ID = "equity";
const ITEMS_PARAM = "items_per_side";

// TODO: units should become user-selectable (a page-level units option); at that
// point use `formatNumber` from utils.js here instead.
function format_billions(value) {
  return `$${(value / 1e9).toFixed(1)}B`;
}

function main() {
  const select = document.getElementById("items-per-side-select");
  const panels = [...document.querySelectorAll("[data-treemap]")].map((container) => ({
    container,
    table: JSON.parse(document.getElementById(container.dataset.source).textContent),
  }));

  function draw(items_per_side) {
    panels.forEach(({ container, table }) => {
      render_treemap(
        container,
        { ...table, rows: table.rows.slice(0, items_per_side) },
        "value",
        {
          format: format_billions,
          className: (row) =>
            row.id === EQUITY_ROW_ID ? "treemap-equity" : `treemap-${container.dataset.treemap}`,
        },
      );
    });
  }

  select.addEventListener("change", () => {
    const url = new URL(window.location.href);
    url.searchParams.set(ITEMS_PARAM, select.value);
    history.replaceState(null, "", url);
    draw(Number(select.value));
  });
  draw(Number(select.value));
}

main();
