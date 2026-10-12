// utils.js assigns to `window` at import time; Node has no window.
globalThis.window ??= {};
