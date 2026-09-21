/**
 * Sole frontend↔backend interface boundary.
 * All `fetch()` calls against backend endpoints live in this file.
 * Other frontend scripts must import from here (or use `window.apiClient`)
 * rather than calling `fetch` themselves.
 *
 * Statement pages currently embed JSON from `build_statement_payload`
 * (`{ ticker, period, statements: { income|balance|cashflow: { summary|standard|detailed: { periods, rows } } } }`).
 * Wizard data fetching is not wired to a live endpoint yet.
 */

async function apiFetch(url, options = {}) {
  const response = await fetch(url, {
    headers: { Accept: "application/json", ...options.headers },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

export async function getWizardPageData(pageSlug, subpageSlug, ticker) {
  // placeholder — not wired to a real endpoint yet
  return {
    ticker,
    period: "annual",
    statements: {},
    page_slug: pageSlug,
    subpage_slug: subpageSlug,
  };
}

export async function getJson(url, options = {}) {
  return apiFetch(url, options);
}

window.apiClient = {
  getWizardPageData,
  getJson,
};
