/**
 * Controller for one <dialog>. The only object that opens or closes it and
 * the only one that listens to its events. Subscribers hear every close,
 * whichever path caused it (Esc, a close button, `form method="dialog"`).
 */
export class DialogController {
  /** @param {HTMLDialogElement} element */
  constructor(element) {
    this._element = element;
    /** @type {Array<(open: boolean) => void>} */
    this._listeners = [];
    element.addEventListener("close", () => {
      this._listeners.forEach((fn) => fn(false));
    });
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

  subscribe(fn) {
    this._listeners.push(fn);
  }
}
