import { Emitter } from "./emitter.js";

/**
 * Controller for one <form>. The only object that listens to its `submit`
 * event; it cancels the browser's navigation and notifies subscribers (with
 * no arguments) instead, so Enter in a field and a submit button share one path.
 */
export class FormController extends Emitter {
  /** @param {HTMLFormElement} element */
  constructor(element) {
    super();
    element.addEventListener("submit", (event) => {
      event.preventDefault();
      this.notify();
    });
  }
}
