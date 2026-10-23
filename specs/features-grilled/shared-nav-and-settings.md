# Spec: Shared nav and Settings drawer

- **Status:** built
- **Depends on:** none of the other grilled specs. Pages built from them (Assets in Use, ROCE, Neff, …) declare their Settings the way this spec describes.
- **Related docs:** `CONTEXT.md` (Setting, Global Setting, Sub-page Setting, View), `specs/STATE.md` (§3 hard rules, §4 wizard identity, §5 Table contract; stale on the adjustment engine, so trust the code), `CLAUDE.md` (shared-file checklist: nothing page-specific in shared files), `specs/vision.md` ("Fund flow View" under Business Understanding).

## Problem Statement

The investor moves between the statements pages and the wizard, but the two
halves feel like different apps. The page/sub-page tab nav exists only in the
wizard; the statements page has none and instead switches statement type in a
dropdown.

Display choices are scattered and forgotten. Each sub-page invents its own
controls (a View select on One-line Answers, a form on Balance Sheet Size,
segmented Basis buttons and fund-flow selects on statements). Some choices
have no control at all: period type is a bare query parameter, and the number
of periods is hardcoded per page (2 on Capitalizing Opex, 5 on Owner Earnings,
10 on statements). Nothing persists, so every navigation resets what the
investor chose, and choosing "quarterly" on one page means nothing on the next.

## Solution

One nav component serves both halves. On the statements side it lists three
Statement pages (Income, Balance, Cash Flow) with no sub-page tabs; on the
wizard side it lists the wizard pages and sub-pages as today. The top site nav
still switches between Statements, Wizard and Screener.

Every display choice becomes a **Setting**, defined once in a central
registry. A **Global Setting** (period type, number of periods, View) applies
everywhere unless a sub-page says it cannot honour it. A **Sub-page Setting**
(basis, current period, previous period, items per side) applies only on the
sub-pages that declare it, and several sub-pages can share one.

A gear icon in the nav opens a **Settings drawer**: the one place to change
Settings. It has a "Global" section and a "This page" section. Global Settings
the current sub-page can't honour are greyed out with a one-line reason;
Sub-page Settings the page doesn't declare are hidden. Changing View applies
immediately; every other change applies when the investor presses Apply. All
in-page display controls are removed.

Settings are remembered in a browser cookie, the same for every ticker, and
survive navigation and restarts. Nothing about Settings is stored on the
server. URLs carry no Settings.

Fund Flow leaves the statements page and becomes a wizard sub-page under
Business Understanding, built on the server.

## User Stories

1. As the investor, I want the same page-tab nav on the statements pages as on the wizard, so that both halves of the app feel like one tool.
2. As the investor, I want Income, Balance and Cash Flow to be pages in the statements nav, so that I switch statements the same way I switch wizard pages.
3. As the investor, I want the statements pages to show no sub-page tab row, so that the nav isn't cluttered with a row of one tab.
4. As the investor, I want each statement page to have its own URL, so that I can bookmark the balance sheet directly.
5. As the investor, I want the bare statements URL for a ticker to open the Income page, so that old links and the site nav still work.
6. As the investor, I want the top site nav (Statements / Wizard / Screener) to keep switching between sections, so that the statements and the wizard stay separate areas.
7. As the investor, I want a gear icon in the nav on every statements and wizard page, so that I always know where to change what I'm looking at.
8. As the investor, I want the gear to open a drawer over the page, so that I can change Settings without leaving the page.
9. As the investor, I want the drawer split into a "Global" section and a "This page" section, so that I know which changes affect every page and which affect only this one.
10. As the investor, I want to choose annual or quarterly once and have every page that supports it follow, so that I don't re-pick the period type on each page.
11. As the investor, I want to choose how many periods to show once and have statements, Capitalizing Opex and Owner Earnings all follow it, so that no page silently hardcodes its own count.
12. As the investor, I want to choose the View (summary, standard, detailed) once and have every page interpret it in its own terms, so that "detailed" shows all rows on a statement and full justifications and sources on One-line Answers.
13. As the investor, I want a View change to apply as soon as I pick it, so that switching detail level feels instant.
14. As the investor, I want every other Setting change to wait for an Apply button, so that changing period type and number of periods together causes one reload and never an invalid in-between state.
15. As the investor, I want a Global Setting the current page can't honour to appear greyed out with a short reason (e.g. "Annual only"), so that I understand why my choice isn't taking effect here.
16. As the investor, I want Sub-page Settings that don't apply to this page to be hidden, so that the drawer only shows what can change this page.
17. As the investor, I want the Basis Setting (reported / adjusted) on the statements pages, Balance Sheet Size and Fund Flow, so that I can see numbers before and after my saved adjustments where that makes sense.
18. As the investor, I want Basis to be one Setting shared by every page that declares it, so that choosing "adjusted" on the income statement carries over to the balance sheet and Fund Flow.
19. As the investor, I want Basis absent from Capitalizing Opex and Owner Earnings, so that those pages keep showing the input to their own adjustment stage.
20. As the investor, I want "adjusted" on a ticker with no saved adjustments to show the reported numbers with the existing "no adjustments" note, so that the choice is never confusingly disabled.
21. As the investor, I want to choose the current period and the previous period once, as "latest", "one back" and so on, so that the choice still makes sense when I switch to a company with a different fiscal year end.
22. As the investor, I want Balance Sheet Size and Fund Flow to share the same current period, so that both pages describe the same balance sheet.
23. As the investor, I want Apply to reject a previous period that isn't older than the current period, with a message in the drawer, so that I don't get a meaningless comparison.
24. As the investor, I want the number of items per side on Balance Sheet Size to be a Setting in the drawer, so that it is remembered like everything else.
25. As the investor, I want Fund Flow to be a wizard sub-page under Business Understanding, right after Balance Sheet Size, so that it sits with the other "understand the balance sheet" views.
26. As the investor, I want Fund Flow to show the current period, the previous period and the change for each balance-sheet row, so that I can see where money moved.
27. As the investor, I want Fund Flow to follow View, Basis, period type and current/previous period, so that it behaves like the balance sheet it is derived from.
28. As the investor, I want my Settings remembered across page loads and app restarts, so that I set them once.
29. As the investor, I want the same Settings for every ticker, so that moving from AAPL to MU keeps my reading preferences.
30. As the investor, I want URLs to carry no Settings, so that links stay clean and a stale bookmark never overrides what I chose.
31. As the investor, I want a Setting that doesn't fit this ticker (e.g. 16 periods when only 10 are cached, or a period offset past the oldest period) to be clamped for this page only, so that one sparse ticker doesn't overwrite my stored choice.
32. As the investor, I want a broken or outdated cookie to fall back to defaults instead of erroring, so that the app always renders.
33. As the investor, I want the defaults to be annual, 10 periods, standard View, reported Basis, current period = latest, previous period = one back and 5 items per side, so that a fresh browser shows sensible pages.
34. As the investor, I want no old in-page controls left on any page, so that there is exactly one place to change Settings.
35. As the investor, I want the wizard landing page to show only the Global section of the drawer, so that it doesn't offer sub-page choices with nothing to apply them to.
36. As the investor, I want Balance Sheet Size to grey out period type ("Annual only"), number of periods ("Single period") and View ("Summary only"), so that I see why those choices don't change it.
37. As the investor, I want One-line Answers to grey out period type and number of periods, so that I see they don't apply to AI answers.
38. As the investor, I want Capitalizing Opex and Owner Earnings to grey out View, so that I see their table layout is fixed.
39. As the investor, I want Fund Flow to grey out number of periods ("Two periods"), so that I see it always compares exactly two.
40. As the developer, I want each Setting defined exactly once (id, label, scope, options or range, default), so that adding a Setting means one registry entry and a declaration on the pages that use it.
41. As the developer, I want each wizard sub-page and each statement page to declare which Sub-page Settings it uses and which Global Settings it cannot honour (with the reason), so that the drawer and the server read the same declaration.
42. As the developer, I want context builders to receive the resolved Settings instead of a bare period string, so that every builder gets validated values from one place.
43. As the developer, I want all Settings validation in one Python place next to the registry, so that the browser never holds a second copy of the rules.
44. As the developer, I want the nav partial to take its page list and URL prefix as parameters, so that it names neither the wizard nor the statements and stays a generic shared file.
45. As the developer, I want the client-side fund-flow builder and the client-side statement/View/Basis switching removed from the statements script, so that there is no second implementation of work the server now does.
46. As the developer, I want the save endpoint to redirect only to same-site paths, so that the redirect can't be abused to send the browser elsewhere.

## Implementation Decisions

### Glossary

- Use **Setting**, **Global Setting**, **Sub-page Setting** and **View** exactly as `CONTEXT.md` defines them. Never call a Setting a "preference": prefs are saved analysis (`adjustment_preferences`).
- View keeps its name everywhere. On One-line Answers, summary and standard show the brief answer; detailed adds justification and source (today's behaviour). The shared name is intended.
- Today's "compare to" becomes `previous_period`; Balance Sheet Size's `as_of` becomes `current_period`.

### Settings registry (new, shared)

- A new registry module defines every Setting: `id`, `label`, `scope` (`global` | `subpage`), allowed options or integer range, default, and whether it applies instantly (only View does).
- Initial Settings:

| id | scope | values | default | applies |
| --- | --- | --- | --- | --- |
| `period` | global | `annual` \| `quarterly` | `annual` | on Apply |
| `num_periods` | global | integer, 1 … the per-period-type cache cap | 10 | on Apply |
| `view` | global | `summary` \| `standard` \| `detailed` | `standard` | instantly |
| `basis` | subpage | `reported` \| `adjusted` | `reported` | on Apply |
| `current_period` | subpage | integer offset ≥ 0 (0 = latest) | 0 | on Apply |
| `previous_period` | subpage | integer offset ≥ 0 (0 = latest) | 1 | on Apply |
| `items_per_side` | subpage | integer, 1 … Balance Sheet Size's max | 5 | on Apply |

- `current_period` and `previous_period` are both offsets from the latest period. Validation rule: `previous_period > current_period`.
- The registry is definitions only. It must not mention any specific page.

### Declarations on pages (identity, in the registries)

- Every wizard sub-page and every statement page carries one declaration: the Sub-page Settings it uses, and a map from each Global Setting it cannot honour to a short reason. Missing declaration = uses no Sub-page Settings, honours every Global Setting.
- These are identity, not logic, so they belong in the registries under the "registry = identity" rule.
- Initial declarations (✔ uses, ✖ greyed with reason, — not declared, so hidden):

| Page | period | num_periods | view | basis | current_period | previous_period | items_per_side |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Statements: Income, Balance, Cash Flow | ✔ | ✔ | ✔ | ✔ | — | — | — |
| One-line Answers | ✖ "Not period-based" | ✖ "Not period-based" | ✔ | — | — | — | — |
| Balance Sheet Size | ✖ "Annual only" | ✖ "Single period" | ✖ "Summary only" | ✔ | ✔ | — | ✔ |
| Fund Flow | ✔ | ✖ "Two periods" | ✔ | ✔ | ✔ | ✔ | — |
| Capitalizing Opex | ✔ | ✔ | ✖ "Detailed only" | — | — | — | — |
| Owner Earnings | ✔ | ✔ | ✖ "Fixed layout" | — | — | — | — |

- The hardcoded period counts on Capitalizing Opex (2) and Owner Earnings (5) are removed; both follow `num_periods`.

### Resolving Settings (new, shared)

- One module resolves the Settings for a page from the raw cookie and that page's declaration: the honoured Global Settings plus the declared Sub-page Settings, with defaults for anything missing.
- An unknown Setting, an invalid option or an out-of-range value falls back to the default **for that render only**. The cookie is never rewritten on read.
- Clamping that depends on the ticker's data (`num_periods` vs cached periods; period offsets past the oldest period) happens where the data is loaded, through one shared helper (the statements route's existing clamp generalised). The stored value stays as chosen.
- Context builders change signature from `(ticker, period)` to `(ticker, settings)`, where `settings` is the resolved Settings object. The default builder ignores it.
- The wizard sub-page route and the statements route stop accepting `period` / `num_periods` query parameters.

### Storage and the save endpoint

- Settings live in a single cookie holding JSON, written only by the server: `HttpOnly`, `SameSite=Lax`, path `/`, long-lived (one year). Nothing about Settings is written to disk or the DB.
- `POST /settings` (form post, no `fetch()`): validates the submitted fields against the registry, merges them into the existing cookie value (fields not submitted are kept), sets the cookie, and redirects with 303 to the `next` path from a hidden field.
- `next` must be a same-site path (starts with a single `/`); anything else redirects to `/`.
- On validation failure (e.g. `previous_period` not older than `current_period`) the cookie is left unchanged. The error is passed back through a short-lived one-shot cookie, and the next render opens the drawer showing the message, then clears it.

### Drawer (shared partial)

- A native `<dialog>` opened by a gear button in the nav. Two forms, both posting to `/settings`:
  - **View form:** the View control alone; it submits on change (instant).
  - **Apply form:** every other Setting shown, plus an Apply button.
- "Global" section: every Global Setting. Ones the page can't honour are disabled, with their reason next to them.
- "This page" section: the page's declared Sub-page Settings. It is absent on the wizard landing page and on pages that declare none.
- The drawer is rendered from the registry plus the page's declaration only. No page-specific branches in the partial.
- All in-page display controls are removed: the One-line Answers View select (and its include partial), the Balance Sheet Size form, the statements page's Statement select, View select, Basis buttons and fund-flow controls. There is no read-only summary line of Settings on the page.

### Shared nav

- The nav partial moves out of the wizard template folder into a shared location. It takes the page list, a URL prefix, the current page/sub-page and the ticker. It contains no reference to the wizard or to statements.
- The sub-page tab row renders only when the current page has sub-pages to list. The statement pages have none.
- The nav hosts the gear button and includes the drawer.

### Statements

- A new statements registry (identity only, same shape as the wizard registry) lists three pages: `income`, `balance`, `cashflow`, with no sub-pages and each with its Settings declaration.
- URLs: `/statements/{ticker}/{statement}`. `/statements/{ticker}` redirects to `income`. An unknown statement slug → 404.
- Each statement page is server-rendered with only its own statement, in the resolved View and Basis, over the resolved number of periods: one `Table` payload instead of today's statements × views × bases bundle.
- The statements script keeps only what it needs to render that one table. Client-side switching of statement type, View, Basis and fund-flow layout is deleted.
- The "adjustments" note stays: shown when Basis is adjusted, including the "no adjustments saved" case, where the adjusted numbers equal the reported numbers.

### Fund Flow (new wizard sub-page)

- Slug `fund-flow`, title "Fund Flow", order 3 under Business Understanding (after Balance Sheet Size).
- Its context builder loads the balance sheet (adjusted when Basis is adjusted), projects it to the resolved View, and returns a `Table` with three columns: current period, previous period, change. Change = current − previous on display signs, the same rule as today's client-side code. Rows and levels as in the balance-sheet projection.
- If the ticker has fewer than two periods once offsets are clamped, or both offsets clamp to the same period, the page shows a "not enough periods" notice instead of the table.

### Documentation to update during implementation

- `specs/STATE.md`: §2 layout (new registries, shared nav/drawer partials), §4 wizard (builder signature, Fund Flow, no `period` query param), statements route and URLs, §5 (statements payload is a single table, Fund Flow no longer client-side).

## Testing Decisions

- **Seams (two, highest available):**
  1. **The Settings module's public interface:** resolve-for-a-page (raw cookie + declaration → resolved Settings) and validate-a-submission (form fields + existing cookie → new cookie value or error). This covers defaults, fallback on bad values, greyed-vs-honoured Global Settings, hidden Sub-page Settings, merging partial submissions and the `previous_period > current_period` rule. These are pure functions, so tests need no HTTP.
  2. **Context builders** (existing seam): the Fund Flow builder returns the expected three-column `Table` for a fixture `StatementSet`, including offsets, clamping, Basis and the "not enough periods" case. Capitalizing Opex and Owner Earnings builders honour `num_periods` from the resolved Settings.
- Good tests assert external behaviour: resolved values, the `Table` payload, the error returned. They don't assert on the template HTML or on internal helper calls.
- Registry consistency test: every Setting id named in any page declaration exists in the Settings registry, and every greyed Global Setting has a non-empty reason.
- Prior art: `tests/test_balance_sheet_size.py` and `tests/test_business_understanding.py` (builder tests against fixture statements), `tests/statement_fixtures.py` (fixture `StatementSet`s), `tests/test_html_renderer.py` (statement payloads), `tests/test_table.py`.
- Route/HTTP tests were first left out. The build removed the few TestClient page tests the repo had. Route tests were then added in `tests/test_settings_routes.py`. They cover the statements redirect and 404, the `next` path check, the cookie attributes, cookie round-trips, refused saves and the drawer per page.

## Out of Scope

- A Page scope for Settings (shared by all sub-pages of one page); add it only when something needs it.
- Per-ticker Settings.
- Storing Settings on the server (DB table or file).
- Settings in URLs, either as overrides or for sharing.
- A read-only summary line of the current Settings on each page.
- A combined nav bar mixing statement pages and wizard pages.
- Moving or redesigning the top site nav, or adding Screener to the shared nav.
- New Settings beyond the table above. Future pages add their own declarations when they are built.
- Inputs (capitalize checkboxes, maintenance %, Target Neff, Scenario values). These are saved analysis, not Settings.

## Further Notes

- The shared files this touches (the nav and drawer partials, the Settings registry and resolver, the wizard registry, the wizard route) fall under the CLAUDE.md shared-file checklist. Every per-page fact (which Settings, which reasons, which builder) lives in a page's declaration or its builder, never in the shared partials or the resolver.
- Clearing browser cookies resets every Setting to its default. That is acceptable for a single-user local app.
- The Balance Sheet Size spec work in `specs/features/dimensional-breakdowns.md` is unaffected: Balance Sheet Size still greys out View ("Summary only") until breakdowns are decided.
