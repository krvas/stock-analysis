import { Emitter } from "./emitter.js";

/**
 * Controller for one button. The only object that listens to its clicks or
 * writes its state (`disabled`, `aria-expanded`). Subscribers are called with
 * no arguments.
 */
export class ActionButton extends Emitter {
  /** @param {HTMLButtonElement} element */
  constructor(element) {
    super();
    this._element = element;
    element.addEventListener("click", () => this.notify());
  }

  /** @param {boolean} disabled */
  setDisabled(disabled) {
    this._element.disabled = disabled;
  }

  /** @param {boolean} expanded */
  setExpanded(expanded) {
    this._element.setAttribute("aria-expanded", String(expanded));
  }
}
