import { Emitter } from "./emitter.js";

/**
 * Controller for one <dialog>. The only object that opens or closes it and
 * the only one that listens to its events. Subscribers hear every close,
 * whichever path caused it (Esc, a close button, `form method="dialog"`).
 */
export class DialogController extends Emitter {
  /** @param {HTMLDialogElement} element */
  constructor(element) {
    super();
    this._element = element;
    element.addEventListener("close", () => this.notify(false));
  }

  set(open) {
    if (open === this._element.open) {
      return;
    }
    if (open) {
      this._element.showModal();
    } else {
      this._element.close();
    }
  }
}
