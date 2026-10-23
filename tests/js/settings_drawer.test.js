import assert from "node:assert/strict";
import { afterEach, test } from "node:test";

import { closeDom, installDom, settle } from "./dom.js";

const NEXT = "/statements/AAPL/income";
const DATA = {
  next_path: NEXT,
  error: null,
  global_fields: [
    {
      id: "period",
      label: "Period",
      widget: "select",
      value: "annual",
      instant: false,
      disabled_reason: null,
      options: [
        { value: "annual", label: "Annual" },
        { value: "quarterly", label: "Quarterly" },
      ],
    },
    {
      id: "view",
      label: "View",
      widget: "select",
      value: "standard",
      instant: true,
      disabled_reason: null,
      options: [
        { value: "standard", label: "Standard" },
        { value: "detailed", label: "Detailed" },
      ],
    },
  ],
  page_fields: [],
};

let win;
let loads = 0;
const realFetch = globalThis.fetch;
afterEach(async () => {
  globalThis.fetch = realFetch;
  await closeDom(win);
});

/**
 * Renders the page the way `_settings_drawer.html` does, stubs fetch with
 * `respond` and navigation, then runs settings_drawer.js against it.
 */
async function page({ data = DATA, respond } = {}) {
  const script =
    data === null
      ? ""
      : `<script type="application/json" id="settings-drawer-data" data-action="/settings">${
          typeof data === "string" ? data : JSON.stringify(data)
        }</script>`;
  win = installDom(`
    <button data-settings-open aria-controls="settings-drawer" aria-expanded="false">Gear</button>
    ${script}
    <dialog id="settings-drawer" aria-labelledby="settings-drawer-title"></dialog>`);
  const posts = [];
  globalThis.fetch = (url, options) => {
    posts.push({ url, body: Object.fromEntries(options.body) });
    return respond ? respond() : Promise.resolve({ type: "opaqueredirect", ok: false });
  };
  const visits = [];
  win.location.assign = (url) => visits.push(url);
  await import(`../../src/static/js/settings_drawer.js?load=${loads++}`);
  const dialog = document.getElementById("settings-drawer");
  const q = (selector) => dialog.querySelector(selector);
  return { dialog, q, posts, visits };
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

test("the gear opens the drawer and marks itself expanded", async () => {
  const { dialog } = await page();
  const gear = document.querySelector("[data-settings-open]");
  assert.equal(dialog.open, false);
  gear.click();
  assert.equal(dialog.open, true);
  assert.equal(gear.getAttribute("aria-expanded"), "true");
  dialog.querySelector("[data-drawer-close]").click();
  await settle();
  assert.equal(dialog.open, false);
  assert.equal(gear.getAttribute("aria-expanded"), "false");
});

test("submitting the form (Apply or Enter) posts the Apply group once, then reloads", async () => {
  const { q, posts, visits } = await page();
  const period = q("#setting-period");
  period.value = "quarterly";
  period.dispatchEvent(new win.Event("change"));
  assert.equal(posts.length, 0);
  q("[data-drawer-form]").requestSubmit();
  await settle();
  assert.deepEqual(posts, [{ url: "/settings", body: { next: NEXT, period: "quarterly" } }]);
  assert.deepEqual(visits, [NEXT]);
});

test("a second submit while a save is in flight is ignored", async () => {
  const pending = deferred();
  const { q, posts, visits } = await page({ respond: () => pending.promise });
  const apply = q("[data-drawer-apply]");
  q("[data-drawer-form]").requestSubmit();
  assert.equal(apply.disabled, true);
  q("[data-drawer-form]").requestSubmit();
  assert.equal(posts.length, 1);
  pending.resolve({ type: "opaqueredirect", ok: false });
  await settle();
  assert.deepEqual(visits, [NEXT]);
});

test("a failed save shows the error, keeps the drawer open and re-enables Apply", async () => {
  const { dialog, q, posts, visits } = await page({
    respond: () => Promise.resolve({ type: "basic", ok: false, status: 500, statusText: "Server Error" }),
  });
  document.querySelector("[data-settings-open]").click();
  q("[data-drawer-form]").requestSubmit();
  await settle();
  const alert = q("[data-drawer-error]");
  assert.equal(alert.hidden, false);
  assert.match(alert.textContent, /Settings were not saved: .*500/);
  assert.equal(q("[data-drawer-apply]").disabled, false);
  assert.equal(dialog.open, true);
  assert.deepEqual(visits, []);

  q("[data-drawer-form]").requestSubmit();
  await settle();
  assert.equal(posts.length, 2);
});

test("changing an instant select posts the instant group right away", async () => {
  const { q, posts, visits } = await page();
  const view = q("#setting-view");
  view.value = "detailed";
  view.dispatchEvent(new win.Event("change"));
  await settle();
  assert.deepEqual(posts, [{ url: "/settings", body: { next: NEXT, view: "detailed" } }]);
  assert.deepEqual(visits, [NEXT]);
});

for (const [name, data] of [
  ["missing", null],
  ["unreadable", "{not json"],
]) {
  test(`${name} drawer data shows the unavailable message and still opens`, async () => {
    const realError = console.error;
    console.error = () => {};
    try {
      const { dialog, q } = await page({ data });
      assert.match(dialog.textContent, /Settings could not be loaded/);
      assert.equal(q("[data-drawer-form]"), null);
      document.querySelector("[data-settings-open]").click();
      assert.equal(dialog.open, true);
    } finally {
      console.error = realError;
    }
  });
}
