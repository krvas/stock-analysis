/**
 * Controller for one button that triggers an action. The only object that
 * listens to its clicks. Subscribers are called with no arguments.
 */
export class ActionButton {
  /** @param {HTMLElement} element */
  constructor(element) {
    /** @type {Array<() => void>} */
    this._listeners = [];
    element.addEventListener("click", () => {
      this._listeners.forEach((fn) => fn());
    });
  }

  subscribe(fn) {
    this._listeners.push(fn);
  }
}
