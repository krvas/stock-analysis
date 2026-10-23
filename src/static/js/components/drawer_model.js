/**
 * Pure state for a field drawer (no DOM): whether it is open, the current
 * value of each field, and whether a save is in flight or failed. Built from
 * the backend's `Drawer.serialize()` payload.
 */

import { coerceNumber } from "../coerce.js";
import { Emitter } from "./emitter.js";

/**
 * @typedef {"global" | "page"} DrawerSection
 * @typedef {{id: string, label: string, widget: "select" | "number",
 *   instant: boolean, options: Array<{value: string, label: string}>,
 *   min?: number, max?: number}} DrawerField
 * @typedef {{type: "open", open: boolean}
 *   | {type: "value", id: string, value: *}
 *   | {type: "saving", saving: boolean}
 *   | {type: "error", error: string | null}} DrawerChange
 */

const SECTION_KEYS = { global: "global_fields", page: "page_fields" };

function normalize(widget, value) {
  if (widget === "number") {
    return coerceNumber(value);
  }
  return value == null ? "" : String(value);
}

export class DrawerModel extends Emitter {
  /**
   * @param {object} data - `{next_path, error, global_fields, page_fields}`.
   * @returns {DrawerModel}
   */
  static fromSerialized(data) {
    return new DrawerModel(data);
  }

  /** @type {Record<DrawerSection, string[]>} */
  #sectionIds;
  /** @type {Map<string, DrawerField>} */
  #fields = new Map();
  /** @type {Map<string, string>} */
  #reasons = new Map();
  /** @type {Map<string, *>} */
  #values = new Map();
  #nextPath;
  #error;
  #open;
  #saving = false;

  constructor(data) {
    super();
    this.#nextPath = data.next_path;
    this.#error = data.error;
    this.#open = data.error != null;
    this.#sectionIds = { global: [], page: [] };
    for (const [section, key] of Object.entries(SECTION_KEYS)) {
      for (const raw of data[key]) {
        const { value, disabled_reason: reason, ...field } = raw;
        this.#fields.set(field.id, Object.freeze(field));
        this.#values.set(field.id, normalize(field.widget, value));
        if (reason != null) {
          this.#reasons.set(field.id, reason);
        }
        this.#sectionIds[section].push(field.id);
      }
    }
  }

  /** @returns {DrawerSection[]} */
  sections() {
    return Object.keys(this.#sectionIds);
  }

  /**
   * @param {DrawerSection} section
   * @returns {DrawerField[]}
   */
  fields(section) {
    return this.#sectionIds[section].map((id) => this.#fields.get(id));
  }

  /** @returns {DrawerField} */
  field(id) {
    return this.#fields.get(id);
  }

  isDisabled(id) {
    return this.#reasons.has(id);
  }

  /** @returns {string | null} Why the field is greyed, or null when enabled. */
  reason(id) {
    return this.#reasons.get(id) ?? null;
  }

  nextPath() {
    return this.#nextPath;
  }

  /** @returns {string | null} The server's refusal or the last failed save. */
  error() {
    return this.#error;
  }

  isOpen() {
    return this.#open;
  }

  setOpen(open) {
    if (open === this.#open) {
      return;
    }
    this.#open = open;
    this.notify({ type: "open", open });
  }

  getValue(id) {
    return this.#values.get(id);
  }

  setValue(id, value) {
    const field = this.#fields.get(id);
    if (!field) {
      throw new Error(`Unknown drawer field: ${id}`);
    }
    const normalized = normalize(field.widget, value);
    if (normalized === this.#values.get(id)) {
      return;
    }
    this.#values.set(id, normalized);
    this.notify({ type: "value", id, value: normalized });
  }

  isSaving() {
    return this.#saving;
  }

  /**
   * Claims the single in-flight save. Clears a previous error.
   *
   * @returns {boolean} false when a save is already running.
   */
  startSave() {
    if (this.#saving) {
      return false;
    }
    this.#saving = true;
    this.notify({ type: "saving", saving: true });
    this.#setError(null);
    return true;
  }

  /** @param {string} message */
  failSave(message) {
    this.#saving = false;
    this.notify({ type: "saving", saving: false });
    this.#setError(message);
  }

  #setError(error) {
    if (error === this.#error) {
      return;
    }
    this.#error = error;
    this.notify({ type: "error", error });
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
    const body = { next: this.#nextPath };
    for (const field of this.#fields.values()) {
      if (!this.isDisabled(field.id) && field.instant === instant) {
        const value = this.#values.get(field.id);
        body[field.id] = value == null ? "" : String(value);
      }
    }
    return body;
  }
}
