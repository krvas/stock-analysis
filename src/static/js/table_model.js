/**
 * Pure data model for column-schema financial tables (no DOM).
 */

const LINKED_GROUP_HANDLERS = {
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

export class TableModel {
  /**
   * @param {object} data - Serialized table JSON from the backend.
   * @returns {TableModel}
   */
  static fromSerialized(data) {
    const model = new TableModel();
    model._ingest(data);
    return model;
  }

  constructor() {
    /** @type {Map<string, object>} */
    this._columns = new Map();
    /** @type {Map<string, object>} */
    this._rows = new Map();
    /** @type {Map<string, object>} */
    this._linkedGroups = new Map();
    /** @type {Array<(rowId: string, colId: string, value: *) => void>} */
    this._listeners = [];
    /** @type {Map<string, Set<string>>} colId -> linked group names */
    this._colToGroups = new Map();
  }

  _ingest(data) {
    this._columns.clear();
    this._rows.clear();
    this._linkedGroups.clear();
    this._colToGroups.clear();

    for (const col of data.columns || []) {
      this._columns.set(col.id, { ...col });
    }

    for (const [name, group] of Object.entries(data.linked_groups || {})) {
      this._linkedGroups.set(name, { ...group });
      for (const colId of [group.base_col, group.pct_col, group.value_col]) {
        if (!this._colToGroups.has(colId)) {
          this._colToGroups.set(colId, new Set());
        }
        this._colToGroups.get(colId).add(name);
      }
    }

    for (const row of data.rows || []) {
      this._rows.set(row.id, {
        id: row.id,
        label: row.label,
        level: row.level,
        is_total: Boolean(row.is_total),
        parent_id: row.parent_id ?? null,
        cells: { ...(row.cells || {}) },
      });
    }
  }

  /**
   * @param {(rowId: string, colId: string, value: *) => void} callback
   */
  subscribe(callback) {
    this._listeners.push(callback);
    return () => {
      const index = this._listeners.indexOf(callback);
      if (index >= 0) {
        this._listeners.splice(index, 1);
      }
    };
  }

  getCell(rowId, colId) {
    const row = this._rows.get(rowId);
    if (!row) {
      return undefined;
    }
    return row.cells[colId];
  }

  setCell(rowId, colId, value) {
    const row = this._rows.get(rowId);
    if (!row) {
      throw new Error(`Unknown row id: ${rowId}`);
    }
    if (!this._columns.has(colId)) {
      throw new Error(`Unknown column id: ${colId}`);
    }

    row.cells[colId] = value;
    this._notify(rowId, colId, value);

    const groupNames = this._colToGroups.get(colId);
    if (!groupNames) {
      return;
    }

    for (const groupName of groupNames) {
      const group = this._linkedGroups.get(groupName);
      const handler = LINKED_GROUP_HANDLERS[group.type];
      if (!handler) {
        continue;
      }
      handler.apply(this, group, colId, rowId);
    }
  }

  _setCellSilent(rowId, colId, value) {
    const row = this._rows.get(rowId);
    if (!row) {
      return;
    }
    row.cells[colId] = value;
    this._notify(rowId, colId, value);
  }

  _notify(rowId, colId, value) {
    for (const listener of this._listeners) {
      listener(rowId, colId, value);
    }
  }

  _coerceNumber(value) {
    if (value === null || value === undefined) {
      return null;
    }
    if (typeof value === "number" && !Number.isNaN(value)) {
      return value;
    }
    const parsed = Number(value);
    return Number.isNaN(parsed) ? null : parsed;
  }

  serialize() {
    return {
      columns: [...this._columns.values()],
      linked_groups: Object.fromEntries(this._linkedGroups.entries()),
      rows: [...this._rows.values()].map((row) => ({
        id: row.id,
        label: row.label,
        level: row.level,
        is_total: row.is_total,
        parent_id: row.parent_id,
        cells: { ...row.cells },
      })),
    };
  }
}
