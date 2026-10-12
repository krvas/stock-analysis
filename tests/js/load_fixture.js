import { readFileSync } from "node:fs";

export function loadFixture(name) {
  const url = new URL(`./fixtures/${name}`, import.meta.url);
  return JSON.parse(readFileSync(url, "utf8"));
}
