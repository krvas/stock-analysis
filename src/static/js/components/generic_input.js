import { coerceNumber } from "../utils.js";

/**
 * Controller for a single table HTML input. This is the only object that
 * creates event handlers for that input. Subscribers receive the coerced value.
 */
export class GenericInput {
  /**
   * @param {string} id
   * @param {ParentNode} parent
   * @param {*} value
   * @param {string} type - HTML input type (e.g. "checkbox", "number", "text").
   */
  constructor(id, parent, value, type) {
    this._type = type;
    /** @type {Array<(value: *) => void>} */
    this._listeners = [];
    this._element = this._createElement(id, parent, type);
    this._value = this._coerce(value);
    this._writeElement(this._value);

    const handleEdit = () => {
      const raw =
        this._type === "checkbox"
          ? this._element.checked
          : this._element.value;
      this.set(raw);
    };
    this._element.addEventListener("input", handleEdit);
    this._element.addEventListener("change", handleEdit);
  }

  _createElement(id, parent, type) {
    const input = document.createElement("input");
    input.type = type;
    input.id = id;
    parent.appendChild(input);
    return input;
  }

  _coerce(value) {
    if (this._type === "checkbox") {
      return Boolean(value);
    }
    if (this._type === "number") {
      return coerceNumber(value);
    }
    return value == null ? "" : String(value);
  }

  _writeElement(coerced) {
    if (this._type === "checkbox") {
      this._element.checked = coerced;
      return;
    }
    if (this._type === "number") {
      this._element.value = coerced == null ? "" : String(coerced);
      return;
    }
    this._element.value = coerced;
  }

  get() {
    return this._value;
  }

  set(value) {
    const coerced = this._coerce(value);
    if (coerced === this._value) {
      return;
    }
    this._value = coerced;
    this._writeElement(coerced);
    this._listeners.forEach((fn) => fn(coerced));
  }

  subscribe(fn) {
    this._listeners.push(fn);
  }
}
