import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";

import { closeDom, installDom } from "./dom.js";

let win;
let postForm;
const realFetch = globalThis.fetch;
beforeEach(async () => {
  win = installDom();
  ({ postForm } = await import("../../src/static/js/api_client.js"));
});
afterEach(async () => {
  globalThis.fetch = realFetch;
  await closeDom(win);
});

function stubFetch(response) {
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return response;
  };
  return calls;
}

test("postForm sends an urlencoded POST that does not follow the redirect", async () => {
  const calls = stubFetch({ type: "opaqueredirect", ok: false, status: 0 });
  await postForm("/settings", { next: "/statements/AAPL/income", period: "annual" });
  assert.equal(calls.length, 1);
  const { url, options } = calls[0];
  assert.equal(url, "/settings");
  assert.equal(options.method, "POST");
  assert.equal(options.redirect, "manual");
  assert.ok(options.body instanceof URLSearchParams);
  assert.equal(options.body.toString(), "next=%2Fstatements%2FAAPL%2Fincome&period=annual");
});

test("postForm resolves on a plain 2xx", async () => {
  stubFetch({ type: "basic", ok: true, status: 200 });
  await postForm("/settings", {});
});

test("postForm throws with the status on a non-redirect failure", async () => {
  stubFetch({ type: "basic", ok: false, status: 400, statusText: "Bad Request" });
  await assert.rejects(postForm("/settings", {}), /400 Bad Request/);
});
