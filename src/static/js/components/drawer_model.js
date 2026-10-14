/**
 * Pure state for a field drawer (no DOM): whether it is open and the current
 * value of each field. Built from the backend's `Drawer.serialize()` payload.
 */

/**
 * @typedef {{type: "open", open: boolean}
 *   | {type: "value", id: string, value: *}} DrawerChange
 */

export class DrawerModel {
  /**
   * @param {object} data - `{next_path, error, global_fields, page_fields}`.
   * @returns {DrawerModel}
   */
  static fromSerialized(data) {
    return new DrawerModel(data);
  }

  constructor(data) {
    this.next_path = data.next_path;
    this.error = data.error;
    this.global_fields = data.global_fields;
    this.page_fields = data.page_fields;
    /** @type {Map<string, object>} */
    this._fields = new Map(
      [...data.global_fields, ...data.page_fields].map((f) => [f.id, f]),
    );
    /** @type {Map<string, *>} */
    this._values = new Map(
      [...this._fields.values()].map((f) => [f.id, f.value]),
    );
    this._open = data.error != null;
    /** @type {Array<(change: DrawerChange) => void>} */
    this._listeners = [];
  }

  field(id) {
    return this._fields.get(id);
  }

  isOpen() {
    return this._open;
  }

  setOpen(open) {
    if (open === this._open) {
      return;
    }
    this._open = open;
    this._notify({ type: "open", open });
  }

  getValue(id) {
    return this._values.get(id);
  }

  setValue(id, value) {
    if (!this._fields.has(id)) {
      throw new Error(`Unknown drawer field: ${id}`);
    }
    if (value === this._values.get(id)) {
      return;
    }
    this._values.set(id, value);
    this._notify({ type: "value", id, value });
  }

  /** @param {(change: DrawerChange) => void} fn */
  subscribe(fn) {
    this._listeners.push(fn);
  }

  /**
   * Send direction: the urlencoded body for one submit. Only enabled fields
   * whose `instant` flag matches, as strings, plus `next`.
   *
   * @param {{instant: boolean}} group
   * @returns {Record<string, string>}
   */
  serialize({ instant }) {
    /** @type {Record<string, string>} */
    const body = { next: this.next_path };
    for (const field of this._fields.values()) {
      if (field.disabled_reason == null && field.instant === instant) {
        const value = this._values.get(field.id);
        body[field.id] = value == null ? "" : String(value);
      }
    }
    return body;
  }

  _notify(change) {
    this._listeners.forEach((fn) => fn(change));
  }
}
