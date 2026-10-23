/**
 * Base class for models and controllers that notify subscribers. Subclasses
 * call `notify`; everyone else only subscribes.
 */
export class Emitter {
  /** @type {Array<(...args: *) => void>} */
  #listeners = [];

  /**
   * @param {(...args: *) => void} fn
   * @returns {() => void} Unsubscribes `fn`.
   */
  subscribe(fn) {
    this.#listeners.push(fn);
    return () => {
      const index = this.#listeners.indexOf(fn);
      if (index >= 0) {
        this.#listeners.splice(index, 1);
      }
    };
  }

  /** @protected */
  notify(...args) {
    this.#listeners.forEach((fn) => fn(...args));
  }
}
