/**
 * Linked-group calculations for TableModel. No DOM.
 */

/**
 * value = base * (pct / 100), or null if either input is missing.
 */
function computeValueFromPct(base, pct) {
  if (base === null || pct === null) return null;
  return base * (pct / 100);
}

/**
 * pct = (value / base) * 100, or null if either input is missing or base is 0.
 */
function computePctFromValue(base, value) {
  if (base === null || value === null || base === 0) return null;
  return (value / base) * 100;
}

export const LINKED_GROUP_HANDLERS = {
  pct_of_base: {
    /**
     * @param {TableModel} model
     * @param {object} group
     * @param {string} changedColId
     * @param {string} rowId
     */
    apply(model, group, changedColId, rowId) {
      const base = model._coerceNumber(model.getCell(rowId, group.base_col));
      const pct = model._coerceNumber(model.getCell(rowId, group.pct_col));
      const value = model._coerceNumber(model.getCell(rowId, group.value_col));

      if (changedColId === group.pct_col) {
        model._setCellSilent(rowId, group.value_col, computeValueFromPct(base, pct));
        return;
      }

      if (changedColId === group.value_col) {
        model._setCellSilent(rowId, group.pct_col, computePctFromValue(base, value));
        return;
      }

      if (changedColId === group.base_col) {
        if (base === null) {
          model._setCellSilent(rowId, group.value_col, null);
          model._setCellSilent(rowId, group.pct_col, null);
          return;
        }
        if (pct !== null) {
          model._setCellSilent(rowId, group.value_col, computeValueFromPct(base, pct));
        } else if (value !== null && base !== 0) {
          model._setCellSilent(rowId, group.pct_col, computePctFromValue(base, value));
        }
      }
    },
  },
};
