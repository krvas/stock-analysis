// View: paints a Table-shaped object as a treemap (area proportional to a column's
// value). No data processing (no filtering, sorting or truncation) and no listeners.

/**
 * Slice-and-dice layout. Items are laid out in the given order; the first takes
 * its share along the current axis, the rest recurse in the remaining rectangle
 * with the axis flipped.
 * @param {number[]} values positive values, largest first
 * @param {number} width
 * @param {number} height
 * @returns {{x: number, y: number, w: number, h: number}[]}
 */
export function slice_and_dice(values, width, height) {
  const rects = [];
  let x = 0;
  let y = 0;
  let w = width;
  let h = height;
  let remaining = values.reduce((sum, v) => sum + v, 0);
  values.forEach((value, i) => {
    if (i === values.length - 1) {
      rects.push({ x, y, w, h });
      return;
    }
    const share = value / remaining;
    if (i % 2 === 0) {
      const cut = w * share;
      rects.push({ x, y, w: cut, h });
      x += cut;
      w -= cut;
    } else {
      const cut = h * share;
      rects.push({ x, y, w, h: cut });
      y += cut;
      h -= cut;
    }
    remaining -= value;
  });
  return rects;
}

function default_format(value) {
  return value.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

/**
 * Draw every row of `table` (Table.serialize() shape, values assumed positive) in
 * the given order into `container` as absolutely positioned boxes.
 * @param {HTMLElement} container
 * @param {{rows: {id: string, label: string, cells: Object}[]}} table
 * @param {string} colId
 * @param {{format?: function(number): string, className?: function(Object): string}} [options]
 */
export function render_treemap(container, table, colId, options = {}) {
  const format = options.format ?? default_format;
  const rows = table.rows;
  container.replaceChildren();
  const rects = slice_and_dice(
    rows.map((row) => row.cells[colId]),
    100,
    100,
  );
  rows.forEach((row, i) => {
    const box = document.createElement("div");
    box.className = ["treemap-box", options.className?.(row)].filter(Boolean).join(" ");
    box.style.left = `${rects[i].x}%`;
    box.style.top = `${rects[i].y}%`;
    box.style.width = `${rects[i].w}%`;
    box.style.height = `${rects[i].h}%`;
    box.title = `${row.label}: ${format(row.cells[colId])}`;
    const label = document.createElement("strong");
    label.textContent = row.label;
    const value = document.createElement("span");
    value.textContent = format(row.cells[colId]);
    box.append(label, value);
    container.append(box);
  });
}
