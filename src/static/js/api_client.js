/**
 * Sole frontend↔backend interface boundary.
 * All `fetch()` calls against backend endpoints live in this file.
 * Other frontend scripts must import from here (or use `window.apiClient`)
 * rather than calling `fetch` themselves.
 *
 * Statement pages embed one `Table.serialize()` payload, hydrated by `table_wiring.js`.
 * Wizard sub-page saves POST JSON via `table_wiring.js` and `postJson`.
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

/**
 * POST an urlencoded form to an endpoint that answers with a redirect (the
 * Post/Redirect/Get routes). Cookies the redirect sets are stored; the caller
 * decides where to navigate.
 *
 * @param {string} url
 * @param {Record<string, string>} fields
 */
export async function postForm(url, fields) {
  const response = await fetch(url, {
    method: "POST",
    body: new URLSearchParams(fields),
    redirect: "manual",
  });
  if (response.type !== "opaqueredirect" && !response.ok) {
    throw new Error(`Request failed: ${response.status} ${response.statusText}`);
  }
}

window.apiClient = {
  getWizardPageData,
  getJson,
  postJson,
  postForm,
};
