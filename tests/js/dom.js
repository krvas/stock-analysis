/**
 * A fresh happy-dom window installed as the global `window`/`document`, the
 * way the browser modules expect. Call in `beforeEach`; `close` in `afterEach`.
 */
import { Window } from "happy-dom";

export function installDom(html = "", url = "http://localhost/statements/AAPL/income") {
  const win = new Window({ url });
  win.document.body.innerHTML = html;
  globalThis.window = win;
  globalThis.document = win.document;
  return win;
}

export async function closeDom(win) {
  await win.happyDOM.close();
  delete globalThis.window;
  delete globalThis.document;
}

/** Lets pending promise callbacks and queued events run. */
export function settle() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}
