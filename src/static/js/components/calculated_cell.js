/**
 * A table cell whose value is computed from other cells of the same model.
 *
 * The formula (`spec.expr`) is defined in Python (`CalculatedCellSpec` in
 * src/models/table.py). Node shapes:
 *   {cell: [rowId, colId]} | {const: number} | {op: "add"|"mul", args: [expr, ...]}
 *
 * Computes once on construction, then recomputes whenever a referenced cell
 * changes in the model. Owns only its own <td>; never writes to the model.
 */

import { coerceNumber, formatNumber, getStatementUnit } from "../utils.js";

const OPS = {
  add: (values) => values.reduce((sum, v) => sum + v, 0),
  mul: (values) => values.reduce((product, v) => product * v, 1),
};

function collectRefs(expr, refs) {
  if ("cell" in expr) {
    refs.add(`${expr.cell[0]}\0${expr.cell[1]}`);
  } else if ("op" in expr) {
    expr.args.forEach((arg) => collectRefs(arg, refs));
  }
  return refs;
}

export class CalculatedCell {
  /**
   * @param {HTMLTableCellElement} slot - The empty `[data-calc-slot]` td.
   * @param {import("./table_model.js").TableModel} model
   * @param {{row_id: string, col_id: string, expr: object}} spec
   */
  constructor(slot, model, spec) {
    this._slot = slot;
    this._model = model;
    this._spec = spec;
    this._refs = collectRefs(spec.expr, new Set());

    this._paint();
    model.subscribe((rowId, colId) => {
      if (this._refs.has(`${rowId}\0${colId}`)) {
        this._paint();
      }
    });
  }

  _evaluate(expr) {
    if ("cell" in expr) {
      const [rowId, colId] = expr.cell;
      return coerceNumber(this._model.getCell(rowId, colId)) ?? 0;
    }
    if ("const" in expr) {
      return expr.const;
    }
    const op = OPS[expr.op];
    if (!op) {
      throw new Error(`Unknown calculated-cell op: ${expr.op}`);
    }
    return op(expr.args.map((arg) => this._evaluate(arg)));
  }

  _paint() {
    this._slot.innerHTML = formatNumber(
      this._evaluate(this._spec.expr),
      getStatementUnit(),
    );
  }
}
