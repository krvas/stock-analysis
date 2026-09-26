/**
 * Pure data model for column-schema financial tables (no DOM).
 */

import { LINKED_GROUP_HANDLERS } from "./linked_groups.js";

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

  get columns() {
    return [...this._columns.values()];
  }

  get rows() {
    return [...this._rows.values()];
  }

  /**
   * @param {(rowId: string, colId: string, value: *) => void} callback
   * @returns {() => void} Unsubscribes this callback.
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

  /**
   * Build the POST body for saving this table back to the backend: only the
   * columns the user can actually edit (kind === "input"), and only those
   * columns' values per row. Not a round-trip mirror of the ingested data —
   * linked groups and static/link column values are intentionally omitted.
   */
  serialize() {
    const inputColumns = [...this._columns.values()].filter(
      (col) => col.kind === "input",
    );
    return {
      columns: inputColumns,
      rows: [...this._rows.values()].map((row) => {
        const cells = {};
        for (const col of inputColumns) {
          cells[col.id] = row.cells[col.id];
        }
        return { id: row.id, cells };
      }),
    };
  }
}
