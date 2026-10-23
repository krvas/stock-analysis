import assert from "node:assert/strict";
import { test } from "node:test";

import { coerceNumber } from "../../src/static/js/coerce.js";
import { Emitter } from "../../src/static/js/components/emitter.js";

class Probe extends Emitter {
  fire(...args) {
    this.notify(...args);
  }
}

test("notify calls subscribers in subscription order with every argument", () => {
  const probe = new Probe();
  const calls = [];
  probe.subscribe((...args) => calls.push(["a", ...args]));
  probe.subscribe((...args) => calls.push(["b", ...args]));
  probe.fire(1, "x");
  assert.deepEqual(calls, [
    ["a", 1, "x"],
    ["b", 1, "x"],
  ]);
});

test("the returned function unsubscribes only that subscriber, once", () => {
  const probe = new Probe();
  const calls = [];
  const offA = probe.subscribe(() => calls.push("a"));
  probe.subscribe(() => calls.push("b"));
  offA();
  offA();
  probe.fire();
  assert.deepEqual(calls, ["b"]);
});

test("coerceNumber maps blanks and junk to null and keeps numbers", () => {
  for (const blank of [null, undefined, "", NaN, "abc"]) {
    assert.equal(coerceNumber(blank), null, String(blank));
  }
  assert.equal(coerceNumber(0), 0);
  assert.equal(coerceNumber(-2.5), -2.5);
  assert.equal(coerceNumber("10"), 10);
  assert.equal(coerceNumber(" 7 "), 7);
});
