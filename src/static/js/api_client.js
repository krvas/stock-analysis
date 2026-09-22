/**
 * Sole frontend↔backend interface boundary.
 * All `fetch()` calls against backend endpoints live in this file.
 * Other frontend scripts must import from here (or use `window.apiClient`)
 * rather than calling `fetch` themselves.
 *
 * Statement pages currently embed JSON from `build_statement_payload`
 * (`{ ticker, period, statements: { income|balance|cashflow: { summary|standard|detailed: { columns, rows, linked_groups } } } }`).
 * Wizard sub-page saves POST JSON via `line_item_tables.js` and `postJson`.
 */

async function apiFetch(url, options = {}) {
  const response = await fetch(url, {
    headers: { Accept: "application/json", ...options.headers },
    ...options,
  });
  if (!response.ok) {
    let message = `Request failed: ${response.status} ${response.statusText}`;
    try {
      const errBody = await response.json();
      if (typeof errBody.detail === "string") {
        message = errBody.detail;
      } else if (errBody.detail != null) {
        message = JSON.stringify(errBody.detail);
      }
    } catch {
      // keep default message when body is not JSON
    }
    throw new Error(message);
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

export async function postJson(url, body, options = {}) {
  return apiFetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...options.headers },
    body: JSON.stringify(body),
    ...options,
  });
}

window.apiClient = {
  getWizardPageData,
  getJson,
  postJson,
};
