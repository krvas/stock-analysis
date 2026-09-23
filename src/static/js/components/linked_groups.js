/**
 * Linked-group calculations for TableModel. No DOM.
 */

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
        if (base === null || pct === null) {
          model._setCellSilent(rowId, group.value_col, null);
        } else {
          model._setCellSilent(rowId, group.value_col, base * (pct / 100));
        }
        return;
      }

      if (changedColId === group.value_col) {
        if (base === null || value === null) {
          model._setCellSilent(rowId, group.pct_col, null);
        } else if (base === 0) {
          model._setCellSilent(rowId, group.pct_col, null);
        } else {
          model._setCellSilent(rowId, group.pct_col, (value / base) * 100);
        }
        return;
      }

      if (changedColId === group.base_col) {
        if (base === null) {
          model._setCellSilent(rowId, group.value_col, null);
          model._setCellSilent(rowId, group.pct_col, null);
          return;
        }
        if (pct !== null) {
          model._setCellSilent(rowId, group.value_col, base * (pct / 100));
        } else if (value !== null && base !== 0) {
          model._setCellSilent(rowId, group.pct_col, (value / base) * 100);
        }
      }
    },
  },
};
