# Per-CIK pinning and cache lookup

Status: proposed. Nothing implemented. Touches only the edgartools company LRU
(`src/api/edgartools/cache.py`) and its two direct consumers
(`src/api/edgartools/source.py`, `src/pipelines/calc_residual_report.py`).
Architecture reference: `specs/STATE.md` §4 (EDGAR cache).

## 1. Problem

The company LRU index (`data/edgartools_cache/company_lru.json`) is keyed by
CIK, but every ticker-facing piece of it assumes one ticker per CIK:

- `touch_company_cache` overwrites the entry's single `ticker` on every call
  (`companies[cik_key] = {**..., "ticker": ticker.upper(), ...}`).
- Pins are tickers (`set_pinned_tickers`, index key `pinned_tickers`), and
  eviction exempts an entry only if `entry.get("ticker") in pinned`.
- `find_cached_cik(cache_dir, ticker)` matches `entry.get("ticker") == ticker`.
- `cached_companies()` returns `{cik: ticker}`; `_companies()` in
  `calc_residual_report.py` has the same shape.

Several listed companies have more than one ticker on one CIK (GOOG/GOOGL,
BRK-A/BRK-B, and similar). They share one set of filings and so one bundle
under `companies/{cik}/`. Failure sequence today:

1. `set_pinned_tickers(["GOOGL"])`.
2. `load_statement_set("GOOGL", ...)` → entry `{ticker: "GOOGL"}`; pinned, safe.
3. `load_statement_set("GOOG", ...)` finds the entry by CIK (`Company(ticker).cik`
   after a `find_cached_cik` miss) and `touch_company_cache` rewrites it to
   `{ticker: "GOOG"}`.
4. The pin no longer matches. The company is now an ordinary LRU entry and is
   evicted once enough other companies are touched, silently deleting data the
   user pinned. Worse for the data test: its pinned tickers exist so test loads
   never evict user companies.

Secondary effects of the same shape: `find_cached_cik(cache_dir, "GOOGL")` returns
`None` after step 3 (a needless `Company(ticker)` SEC lookup in
`load_statement_set`), and the calc-residual report drops a ticker silently,
because `{cik: ticker}` can hold only one.

## 2. Goals

1. A pin on any ticker of a CIK protects that company's cache from eviction,
   regardless of which of its tickers was loaded last.
2. `find_cached_cik` resolves every ticker ever recorded for a CIK.
3. `calc_residual_report` can report (and filter by) every ticker of a cached
   CIK; no ticker disappears.
4. Existing `company_lru.json` files keep working with no manual step and no
   loss of pins or LRU order.

## 3. Non-goals

- **No pin-management UI or CLI.** The user keeps no pin list besides the
  gitignored data-test file `tests/data_test_tickers.txt`, written through
  `set_pinned_tickers` in `tests/test_edgar_data.py`. Pins stay a programmatic
  API.
- **No change to the public pin API shape.** Pins stay ticker strings
  (`set_pinned_tickers(tickers)` / `pinned_tickers()`), because a pin must be
  settable before the company has an entry, i.e. before its CIK is known
  without a network call (current documented behaviour).
- **No ticker → CIK resolution via SEC at pin time**, and no discovery of
  sibling tickers. A sibling is known only once it has been loaded.
- No change to bundle layout, `CACHE_SCHEMA_VERSION`, staleness rules, or
  `load_statement_set`'s signature.
- No share-class-specific data handling (per-class share counts, etc.). The
  statements are per company.
- No unification of ticker normalization (`BRK.B` vs `BRK-B`); see open
  questions.

## 4. Requirements

### P0

**R1. Index entry holds a set of tickers.** Entry shape becomes
`{"tickers": [sorted, uppercased, unique], "last_accessed": iso}`.
`touch_company_cache` unions the new ticker into the existing list; it never
removes one. Public signature of `touch_company_cache` is unchanged.

**R2. Eviction is per CIK.** An entry is pinned iff
`set(entry["tickers"]) & set(index["pinned_tickers"])` is non-empty. Pinned
entries are excluded from the LRU ordering and from the `max_companies` count
(same semantics as today). A pin therefore covers the whole company, including
sibling tickers the user never pinned.

**R3. `find_cached_cik` matches any recorded ticker** (case-insensitive) and
returns the CIK key, or `None`. If a ticker appears under more than one CIK
(stale data after a ticker reassignment), return the most recently accessed
entry and log a warning.

**R4. `cached_companies` returns all tickers per CIK:**
`dict[str, tuple[str, ...]]` (`{cik: sorted tickers}`), index only, as today.
Entries with no tickers are skipped.

**R5. `calc_residual_report` handles multi-ticker CIKs.** `_companies` returns
the same `{cik: tuple[ticker, ...]}` shape. With explicit `tickers`, a CIK is
reported once per requested ticker that maps to it (so `GOOG GOOGL` yields both
labels). With no tickers (whole index), every ticker of every CIK is reported.
Rows are duplicated per ticker label; bundle reads happen once per CIK
(read once, label many). Summary and `--compare-viewer` output are otherwise
unchanged. Each ticker is a distinct `ticker` value in `_GROUP_KEYS`.

**R6. Migration of existing `company_lru.json`.** Done in `_load_index`, lazily
and idempotently, no version flag required:

- Entry with legacy `"ticker": "X"` and no `"tickers"` → `"tickers": ["X"]`,
  legacy key dropped from the in-memory index.
- Entry with both keys (partial write by an older/newer build) → union, drop
  `ticker`.
- Entry with neither, or an invalid type → `tickers: []`; the entry is kept
  (its bundle files still exist and it still participates in LRU, as today
  where a tickerless entry is simply unpinned).
- `pinned_tickers` handling is unchanged.
- The rewritten shape reaches disk on the next `_save_index` (next
  `touch_company_cache` or `set_pinned_tickers`); reading alone does not
  rewrite the file. Eviction log line uses `"/".join(tickers)`.

**R7. Downgrade is out of scope but must not corrupt.** An old build reading a
new index would see no `ticker` and treat every entry as unpinned. Acceptable
for a single-user local project; documented, not mitigated.

### P1

- `source.load_statement_set`: after resolving `company.cik`, call `_touch`
  with the requested ticker (already the case). No code change expected beyond
  consuming R3, but confirm the `int(cached_cik) != int(company.cik)` branch
  still behaves when the ticker is a newly seen sibling (see AC-6).
- Update `STATE.md` §4/§6 and the `cache.py` module docstring (they say
  "pinned tickers ... exempt") to describe per-CIK semantics.

### P2 (design must not preclude)

- Pinning by CIK directly (`pinned_ciks`) if a pin UI or CLI is ever added.
- Pre-resolving sibling tickers from edgartools' company metadata.

## 5. Index schema

Before:

```json
{
  "companies": {"1652044": {"ticker": "GOOG", "last_accessed": "2026-10-01T12:00:00+00:00"}},
  "pinned_tickers": ["GOOGL"]
}
```

After (the file stays as it is after the first save; `pinned_tickers` is
untouched):

```json
{
  "companies": {"1652044": {"tickers": ["GOOG", "GOOGL"], "last_accessed": "2026-10-01T12:00:00+00:00"}},
  "pinned_tickers": ["GOOGL"]
}
```

Note the migrated legacy entry above holds only `GOOG`; `GOOGL` is added when it
is next loaded. The pin on `GOOGL` does not protect a migrated GOOG-only entry
until then (see Risks).

## 6. Affected code

| File | Change |
| --- | --- |
| `src/api/edgartools/cache.py` | `_load_index` migration (R6); `touch_company_cache` ticker union + per-CIK pinned test (R1, R2); `find_cached_cik` (R3); `cached_companies` (R4); `_evict_company` log line; docstring. Optional small helper `_entry_tickers(entry) -> list[str]` (private to the module) |
| `src/pipelines/calc_residual_report.py` | `_companies` and `collect_residuals` loop (R5) |
| `src/api/edgartools/source.py` | No expected change; verify only (P1) |
| `tests/test_edgartools_cache.py` | Update `test_cached_companies_lists_index` (shape change); add tests below |
| `tests/test_calc_residual_report.py` | Add multi-ticker report test |
| `specs/STATE.md`, `cache.py` docstring | Doc update (P1) |

`tests/test_edgar_data.py` needs no change: it calls `set_pinned_tickers`,
whose signature is unchanged.

## 7. Acceptance criteria / test cases

Cache-level tests use `tmp_path` and `touch_company_cache`, no network.

- **AC-1 (the bug).** Given `set_pinned_tickers(["GOOGL"])`, `max_companies=1`;
  touch CIK 1652044 as `GOOGL`, then as `GOOG`, then touch two unrelated CIKs.
  Then the GOOG/GOOGL entry is not evicted (not in the returned list; its
  `companies/1652044` dir still exists), and its entry `tickers ==
  ["GOOG", "GOOGL"]`.
- **AC-2.** Pin `GOOG` only, touch the CIK as `GOOGL` only (sibling not pinned).
  Entry is exempt from eviction (per-CIK semantics: any ticker in the pin set).
- **AC-3.** Pinned-company entries do not count toward `max_companies` (the
  existing test at `test_edgartools_cache.py` ~L449–470 still passes with the
  new entry shape).
- **AC-4.** `find_cached_cik(cache_dir, "goog")` and `("GOOGL")` both return
  `"1652044"`; an unknown ticker returns `None`.
- **AC-5.** Same ticker under two CIKs: returns the newer `last_accessed` CIK and
  emits a warning (caplog).
- **AC-6.** `source.load_statement_set` path (mocked, mirroring
  `tests/test_edgartools_source.py` ~L1080): ticker `GOOGL` already indexed;
  loading `GOOG` with a fresh bundle misses `find_cached_cik` once, resolves
  `Company("GOOG").cik` to the same CIK, serves the cached bundle with no
  filing-list request, and touches the CIK with `ticker="GOOG"`; afterwards
  `find_cached_cik(..., "GOOG")` hits and no `Company(...)` call is needed.
- **AC-7.** `cached_companies` returns `{"1652044": ("GOOG", "GOOGL"), ...}`.
- **AC-8 (migration).** Write a legacy file (`{"companies": {"320193":
  {"ticker": "AAPL", "last_accessed": ...}}, "pinned_tickers": ["AAPL"]}`) by
  hand. `find_cached_cik("AAPL")` == `"320193"`, `cached_companies` ==
  `{"320193": ("AAPL",)}`, pin still protects it, and the file on disk is
  unchanged after read-only calls. After one `touch_company_cache`, the file
  contains `tickers` and no `ticker`. Running the migration twice is a no-op.
  Also cover: entry with both keys, entry with neither, entry with
  `ticker: null`/non-string.
- **AC-9 (report).** Index with one CIK holding GOOG and GOOGL and a valid
  bundle: `collect_residuals(["GOOG", "GOOGL"])` yields rows for both ticker
  values with identical residuals; `collect_residuals(None)` also contains both;
  `collect_residuals(["GOOGL"])` contains only GOOGL. `read_period_bundle` is
  called once per CIK per period (patch/spy).
- **AC-10 (regression).** Existing tests in `test_edgartools_cache.py`,
  `test_edgartools_source.py`, `test_calc_residual_report.py` pass, aside from
  the deliberate shape change in AC-7.
- **Negative:** `touch_company_cache` never drops a previously recorded ticker;
  `set_pinned_tickers` still evicts nothing and still preserves `companies`.

## 8. Risks

- **Pin protects only recorded siblings' company, and only after the pinned
  ticker is recorded.** Migrated legacy entries hold one ticker. Scenario:
  legacy index has `{ticker: "GOOG"}`, pin is `GOOGL`, nothing has loaded
  `GOOGL` since: the pin still does not match and eviction can occur. This is
  inherent to ticker pins without a ticker→CIK map. Mitigation: loading the
  pinned ticker through the app (as the data test does) adds it. Not fixed in
  this feature (non-goal: SEC resolution at pin time).
- **Test churn.** `cached_companies` return type changes (callers: only
  `calc_residual_report`; one test). Low.
- **Wider pin effect.** Pinning one class pins the company, which is the
  intent, but a user who "unpins" by removing a ticker from the list while
  its sibling stays pinned will see the company stay pinned. Acceptable.
- **Report duplication.** Duplicated rows per ticker may surprise someone
  summing the whole-index report; the `ticker` label makes this visible.
- **Lazy migration** leaves legacy shape on disk until the next write. Readers
  must always go through `_load_index` (already true; keep it that way).
- **Concurrent writers** (data test + app) can lose a ticker in a
  read-modify-write; unchanged from today's single-writer assumption.

## 9. Suggested implementation order

1. Failing tests first (repo convention): AC-1, AC-2, AC-4, AC-8 in
   `test_edgartools_cache.py`.
2. `_load_index` migration + `_entry_tickers` helper (R6).
3. `touch_company_cache` ticker union and per-CIK pin test (R1, R2); AC-1–3.
4. `find_cached_cik` (R3) and `cached_companies` (R4); AC-4, 5, 7; fix the
   existing shape test.
5. `calc_residual_report._companies` / `collect_residuals` (R5); AC-9.
6. Source-level test AC-6; confirm `source.py` needs no change.
7. Docs: `cache.py` docstring, `STATE.md` §4/§6.
8. `.venv/bin/ruff check .` and `.venv/bin/ruff format --check .`, then
   `pytest` (default selection; `-m data` is optional manual verification
   with GOOG and GOOGL added to `tests/data_test_tickers.txt`).

Steps 1–4 and 5 are separable commits.

## 10. Assumptions / open questions

Assumptions (made without asking the user):

- Pins remain ticker strings; per-CIK matching happens at eviction time via the
  entry's ticker set (a pin must precede the company's first load).
- Reporting every ticker of a CIK (duplicated rows) is preferable to one
  combined label such as `GOOG/GOOGL`, because it keeps the `ticker` filter
  and group keys simple.
- Lazy in-memory migration on read, persisted on next write, is sufficient;
  no `index_version` field or one-shot migration script.
- No `CACHE_SCHEMA_VERSION` bump: bundles are unchanged.
- Downgrade compatibility is not required (single user, local).

Open questions (non-blocking):

- **Ticker normalization** (`BRK-B` vs `BRK.B`): does edgartools' `Company()`
  accept both, and which does the user type? Today each spelling is a separate
  string. Could be normalized in `_normalize_tickers`; deliberately excluded
  here. Owner: user.
- **Pre-seeding siblings**: is closing the "unrecorded sibling" gap worth an
  SEC lookup at pin time (edgartools may expose a company's tickers)? Owner:
  user/engineering.
- **Duplicate-ticker conflict** (R3): warn-and-pick-newest versus drop the older
  entry's ticker on touch. Owner: engineering.
