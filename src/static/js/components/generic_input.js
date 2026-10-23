import { coerceNumber } from "../coerce.js";
import { Emitter } from "./emitter.js";

/**
 * Controller for a single form control (table cells, drawer fields). This is
 * the only object that creates event handlers for that control. Subscribers
 * receive the coerced value.
 */
export class GenericInput extends Emitter {
  /**
   * @param {string} id
   * @param {ParentNode} parent
   * @param {*} value
   * @param {string} type - HTML input type ("checkbox", "number", "text") or "select".
   * @param {{choices?: Array<{value: string, label: string}>,
   *   attributes?: Record<string, string | number | boolean | null>}} [options]
   *   `choices` are a select's options. `attributes` are set on the element;
   *   `true` sets a boolean attribute, `false` and `null` are skipped.
   */
  constructor(id, parent, value, type, { choices = [], attributes = {} } = {}) {
    super();
    this._type = type;
    this._element = this._createElement(id, parent, type, choices, attributes);
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

  _createElement(id, parent, type, choices, attributes) {
    let element;
    if (type === "select") {
      element = document.createElement("select");
      choices.forEach(({ value, label }) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = label;
        element.appendChild(option);
      });
    } else {
      element = document.createElement("input");
      element.type = type;
    }
    element.id = id;
    for (const [name, value] of Object.entries(attributes)) {
      if (value === true) {
        element.setAttribute(name, "");
      } else if (value !== false && value != null) {
        element.setAttribute(name, String(value));
      }
    }
    parent.appendChild(element);
    return element;
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
    this.notify(coerced);
  }
}
