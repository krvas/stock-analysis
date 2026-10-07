# Stale-bundle revalidation TTL

Status: proposed. Nothing implemented. Touches the edgartools cache
(`src/api/edgartools/cache.py`), `load_statement_set` in
`src/api/edgartools/source.py`, and `src/config.py`. Architecture reference:
`specs/STATE.md` §4 (EDGAR cache). Interacts with
`specs/features/cache-atomicity-and-concurrency.md` (both touch `meta.json`; see
R6 and Risks) and is otherwise independent of
`specs/features/ticker-cik-pinning.md`.

## 1. Problem

A bundle is *stale* when its stored `latest_filing_date` is older than the period
max age (`is_period_bundle_stale`: `EDGARTOOLS_ANNUAL_CACHE_MAX_AGE_MONTHS`,
default 12; `EDGARTOOLS_QUARTERLY_CACHE_MAX_AGE_MONTHS`, default 3). Stale does
not mean wrong: it means "SEC might have a newer filing, go look". Verified by
reading `load_statement_set` (`source.py`):

1. `read_period_bundle` returns `stale=True`, so the fast path
   (`not cached.stale`) is skipped.
2. `Company(ticker)` is constructed (SEC round trip, unless edgartools has it
   cached).
3. `company.get_filings(form=..., amendments=False).head(max_periods)` runs (a
   second SEC request; quarterly bundles also run `get_filings(form="10-K")` in
   `_freshness_date`).
4. `cached.latest_filing_date == latest_filing_date` → serve the stale bundle.
   **Nothing is written**, so nothing records that the check happened.

For a company that simply has not filed recently (delisted, acquired, shell,
or just between filings: an annual bundle is "stale" for up to a year after
its last 10-K regardless of anything SEC does), steps 2-3 repeat on **every
request, forever**. A page view that should be a local parquet read pays two
to three SEC requests, adds latency, burns SEC rate-limit budget, and fails
outright when offline (today `Company` raising `ConnectionError` propagates;
the existing test `test_stale_bundle_is_served_when_sec_is_unreachable` in
`tests/test_edgartools_source.py` specifies the intended fallback and currently
fails). The wizard and the data tests issue several `load_statement_set` calls
per session, multiplying the cost.

## 2. Goals

1. A stale-but-current bundle costs **zero** SEC requests when it was confirmed
   current within the revalidation TTL (default 1 day).
2. At most one SEC freshness check per `(cik, period)` per TTL window, however
   many requests arrive.
3. A newer filing, a schema bump, or a corrupt bundle still forces a rebuild
   exactly as today; the TTL only ever *skips a "nothing new" confirmation*.
4. If the freshness check fails (SEC unreachable), the stale bundle is served
   with a warning instead of an error.
5. Existing bundles on disk keep working without a schema bump.

## 3. Non-goals

- **No change to what "stale" means** (`is_period_bundle_stale`, the two
  max-age settings, `read_period_bundle`'s `stale` flag). Staleness stays a
  function of `latest_filing_date` only; the TTL gates only the SEC check.
- **No TTL for fresh bundles.** Fresh bundles never hit SEC and still do not.
- **No background refresh or "refreshing" UI** (parked P2 in the concurrency
  spec). The check stays synchronous in the request.
- **No persistent negative caching of failed checks** beyond what R5 says;
  an unreachable SEC is retried on the next request (see open question 3).
- **No change to rebuild logic, `MAX_PERIODS_BY_PERIOD`, or the
  `Statement`/`StatementSet` contracts**, and no route change.
- **No cross-bundle sharing** of the check: annual and quarterly bundles of one
  company are checked independently (they compare different filings).

## 4. Requirements

### P0

**R1. Record the check.** When `load_statement_set` has just confirmed a stale
cached bundle is still current (`cached.latest_filing_date == latest_filing_date`,
today's "serving the stale cached bundle" branch), it records `checked_at`, a
UTC ISO-8601 timestamp (`datetime.now(UTC).isoformat()`, same format as the
existing `_utc_now_iso`), in that bundle's `meta.json`. Confirmation *after a
rebuild* also sets it: `save_period_bundle` writes `checked_at` = build time
(the build just proved currency), so a freshly rebuilt bundle that ages into
staleness starts its TTL window from the build, not from `None`.

**R2. Skip the SEC check inside the TTL.** After reading a stale bundle,
`load_statement_set` serves it immediately, with no `setup_edgartools()` need,
no `Company(...)`, no `get_filings`, when `checked_at` is present and
`now - checked_at < EDGARTOOLS_REVALIDATE_TTL`. It still calls `_touch` so LRU
recency stays correct. The CIK used is the one from `find_cached_cik`; the
`int(cached_cik) != int(company.cik)` re-resolution path only exists when
`Company` was called and is naturally not reached.

**R3. Configurable TTL.** `src/config.py` gains
`EDGARTOOLS_REVALIDATE_TTL_HOURS` (env var of the same name, default `24`,
`max(0, int(...))` like its neighbours; config lives only in `config.py`).
`0` disables skipping (every stale request revalidates, today's behaviour,
useful for the data tests and debugging). `cache.py` converts it to a
`timedelta` internally; the unit is hours because the existing settings are
integers and sub-hour TTLs have no use case.

**R4. What still forces work.** The TTL never suppresses any of these:
- a missing/invalid/old-schema/corrupt bundle (`read_period_bundle` returns
  `None` → rebuild, unchanged);
- `checked_at` missing, unparseable, or **in the future** (clock skew) → treated
  as expired (revalidate);
- TTL expired → one SEC check, exactly today's flow;
- a SEC check that finds a newer filing → rebuild (unchanged), and the new
  bundle gets a fresh `checked_at` via R1.

**R5. Offline fallback.** When `cached` is a stale, readable bundle and the
freshness check (`Company(ticker)`, `get_filings`, or `_freshness_date`) raises
(`ConnectionError`/`OSError`/any `Exception` from edgartools' network layer, as
those errors are not a stable type), `load_statement_set` logs a WARNING naming
ticker, period and the error, serves the stale bundle, and **does not** write
`checked_at` (a failed check is not a confirmation, so the next request retries
SEC). With no cached bundle the error still propagates (cold cache, per the
existing test). The fallback covers only the freshness check, **not** the
rebuild: once a newer filing was seen, a failure in `XBRLS.from_filings` or
the build propagates as today (a half-observed newer filing must not be
silently masked by serving old data). Making
`test_stale_bundle_is_served_when_sec_is_unreachable` pass is part of this
feature's acceptance.

**R6. Ownership of the meta write.** A new function in `cache.py`:

```python
def touch_period_bundle_checked(
    *,
    cik: int | str,
    period: PeriodType,
    expected_latest_filing_date: date,
    cache_dir: Path | None = None,
    now: datetime | None = None,
) -> bool: ...
```

It is the **only** writer of `checked_at` outside `save_period_bundle`. Reuse
of `save_period_bundle` is rejected: that rewrites six parquet files for a
timestamp change (and, once the concurrency spec lands, creates a whole new
bundle directory). `touch_period_bundle_checked`:
- reads the current `meta.json`; if it is missing/invalid, the
  `schema_version` is not `CACHE_SCHEMA_VERSION`, or its `latest_filing_date`
  differs from `expected_latest_filing_date` (the bundle was rebuilt or evicted
  between our read and now), it writes **nothing** and returns `False`. This
  guard is what stops a slow "still current" confirmation from overwriting
  a newer bundle's meta with stale values;
- otherwise writes the same meta dict with `checked_at` set (every existing key,
  including a future `bundle_id`, preserved untouched) via a uniquely named temp
  file (`meta.json.{uuid4hex}.tmp`) plus `os.replace`;
- never creates a directory or a file for a missing bundle;
- never raises for I/O errors: logs a WARNING and returns `False` (failing to
  record the check must not fail the request, which already has a bundle to
  serve; the cost is one extra SEC check next time).

`source.py` calls it and does not touch `meta.json` itself.

**R7. Tolerant reads, no schema bump.** `checked_at` is optional.
`CACHE_SCHEMA_VERSION` stays 7: bumping it would discard every user bundle and
trigger a full SEC rebuild per company (minutes each) for a field whose absence
has a safe meaning ("never confirmed → check now"). Old bundles are upgraded
lazily: the first stale request after deploy does one SEC check, then records
`checked_at`. `CachedStatementSet` gains `checked_at: datetime | None`
(`None` when absent or unparseable; unparseable also logs at INFO, no discard:
a bad timestamp is not corrupt data). The module docstring's meta line
becomes `# schema_version, period, latest_filing_date, checked_at (optional)`.

**R8. Clock injection.** Mirrors `reference` in `is_period_bundle_stale`.
`now: datetime | None = None` (default `datetime.now(UTC)`) on
`touch_period_bundle_checked` (the value written) and on a new pure helper:

```python
def is_recheck_due(
    checked_at: datetime | None,
    *,
    now: datetime | None = None,
    ttl: timedelta | None = None,
) -> bool: ...
```

`ttl` defaults from config. Due when `checked_at is None`, `ttl <= 0`,
`checked_at > now`, or `now - checked_at >= ttl`. `read_period_bundle` does not
gain a `now` parameter (it only reports `checked_at`; the decision lives in
`source.py` via `is_recheck_due`, so cache reads stay free of SEC-policy).
`load_statement_set` has no public clock parameter; tests monkeypatch
`source.is_recheck_due`'s default or patch `cache.datetime`/pass `now` at the
cache-level functions (§7). Naive timestamps are normalized to UTC.

### P1

**R9. Observability.** INFO log when a stale bundle is served inside the TTL
("revalidation skipped, last checked at ..."), alongside the existing "No filing
newer than" INFO. WARNING on fallback (R5) and on a failed meta write (R6).

**R10. Report visibility.** `calc_residual_report` keeps ignoring `checked_at`
for behaviour (see §6) but includes it in the existing stale warning so a
reader can tell "stale and recently confirmed current" from "stale and never
confirmed".

### P2 (design must not preclude)

- Negative caching of a failed check with a much shorter TTL (e.g. 5 minutes),
  so an offline laptop does not pay a connection timeout per request.
- Per-period TTLs, or `EDGARTOOLS_REVALIDATE_TTL_HOURS` overridable per ticker.
- Background revalidation while serving the stale bundle (the concurrency
  spec's P2).

## 5. Design options

**A. `checked_at` inside `meta.json` (recommended).** The check result describes
the bundle, lives and dies with it (rebuild, delete, eviction all reset it for
free), and needs no new file or index schema. Cost: a meta rewrite, covered by
R6.

**B. `last_checked` per company in `company_lru.json`.** Avoids touching bundle
meta, but the index is shared mutable state with the pinning and concurrency
specs, is per-CIK while the check is per `(cik, period)`, and would survive a
bundle rebuild/delete with a now-wrong confirmation. Rejected.

**C. In-memory TTL cache (dict of `(cik, period) → time`).** Trivial and no disk
writes, but lost on every restart and invisible to the CLI/data-test processes
(each would re-check), which is most of the observed cost. Possible *in
addition* only if disk writes prove a problem; not needed.

**D. Reuse `save_period_bundle` to refresh meta.** Rewrites everything and
changes the bundle on every confirmation; rejected (R6).

## 6. Affected code

| Where | Change |
| --- | --- |
| `src/config.py` | `EDGARTOOLS_REVALIDATE_TTL_HOURS` (default 24, `max(0, ...)`), commented like the max-age settings |
| `src/api/edgartools/cache.py` | `touch_period_bundle_checked`, `is_recheck_due`, `CachedStatementSet.checked_at`; `read_period_bundle` parses optional `checked_at`; `save_period_bundle` writes `checked_at`; docstring; no change to `CACHE_SCHEMA_VERSION` |
| `src/api/edgartools/source.py` `load_statement_set` | TTL skip before `setup_edgartools`/`Company`; call `touch_period_bundle_checked` in the "no newer filing" branch; wrap the freshness check in the offline fallback; update the docstring ("a stale bundle costs one filing-list request" → "at most one per TTL") |
| `src/api/edgartools/__init__.py` | Export only if `source.py` imports across the package boundary in a way STATE.md §3 requires (the new functions are imported from `cache` directly like `read_period_bundle` today) |
| `src/pipelines/calc_residual_report.py` | No behaviour change. `prune=False` reads, never writes `checked_at`, never does SEC. Optionally (R10) append `checked_at` to its stale warning |
| `tests/test_edgar_data.py` | No change in behaviour; a stale-but-current bundle now skips SEC for a day. Document `EDGARTOOLS_REVALIDATE_TTL_HOURS=0` as the way to force revalidation for a data run (module docstring only) |
| `tests/test_edgartools_cache.py`, `tests/test_edgartools_source.py` | New tests (§7); existing tests keep passing, except see below |
| `specs/STATE.md` §4, `cache.py` docstring | Doc update: `checked_at`, TTL, fallback |

Existing test impact: `test_stale_bundle_without_newer_filing_is_served_from_cache`
seeds a bundle via `_seed_cache` (presumably no `checked_at`) and asserts
`get_filings` was called; with `checked_at` absent R2 does not skip, so it
passes unchanged and then also asserts the new `checked_at` (add to its
asserts). Any test seeding via `save_period_bundle` will now have `checked_at`
= build time and must pass `now`/TTL 0 or backdate meta to exercise the SEC
path; `_seed_cache` should gain an optional `checked_at` argument.

Residual report and data test behaviour in detail:
- **`calc_residual_report`** is read-only by contract (`prune=False`). It never
  calls `touch_period_bundle_checked`, never contacts SEC, and its "stale;
  reporting on it anyway" path is unchanged, because the report's job is to
  describe what is on disk. It must tolerate bundles with and without
  `checked_at` (it only reads the `CachedStatementSet` fields it uses).
- **`tests/test_edgar_data.py`** (`pytest -m data`) calls `load_statement_set`
  for each test ticker; stale-but-current bundles it touches now record
  `checked_at` and are not re-checked for 24 h, which makes repeat data runs
  faster. A data run wants no hidden skipping when someone is specifically
  verifying new filings were picked up; set the env var to `0`. Default
  suites with no network are unaffected (they mock `_sec`).

## 7. Acceptance criteria / test cases

Cache-level (`tests/test_edgartools_cache.py`, `tmp_path`, no network, `now`
injected):

- **AC-1 (write).** Save a bundle, then
  `touch_period_bundle_checked(..., expected_latest_filing_date=d, now=T)`
  returns `True`; `meta.json` has `checked_at == T.isoformat()` and every other
  key (`schema_version`, `period`, `latest_filing_date`) is unchanged; parquet
  files untouched (mtimes unchanged); no `*.tmp` left.
- **AC-2 (guard).** After a rebuild with a different `latest_filing_date`, a
  touch carrying the old `expected_latest_filing_date` returns `False` and
  leaves meta byte-identical (no clobbering of the new bundle).
- **AC-3 (missing/old schema/corrupt meta).** Touch on a missing bundle returns
  `False` and creates nothing; on `schema_version=-1` or invalid JSON returns
  `False` and rewrites nothing.
- **AC-4 (tolerant read).** A bundle with no `checked_at` reads with
  `checked_at is None` and is not discarded; an unparseable `checked_at`
  reads as `None`, bundle kept (INFO log).
- **AC-5 (save sets it).** `save_period_bundle` followed by
  `read_period_bundle` yields `checked_at` within a second of build time.
- **AC-6 (`is_recheck_due`).** Table: `None` → due; `now - 1h` with 24 h TTL →
  not due; exactly 24 h → due; 25 h → due; future (`now + 1h`) → due; TTL 0 →
  always due; naive timestamp treated as UTC.
- **AC-7 (I/O failure).** Patch `os.replace` to raise `OSError`: touch returns
  `False`, logs a WARNING, raises nothing, and the old meta is intact.

Source-level (`tests/test_edgartools_source.py`, reusing `_sec`, `_seed_cache`,
`_patch_sec_filings`; the clock via patching `source.is_recheck_due`'s `now`
or `cache.datetime`):

- **AC-8 (check recorded).** Stale bundle, no newer filing, no `checked_at`:
  served from cache, `xbrls.from_filings` not called, `meta.json` now has
  `checked_at`, `latest_filing_date` unchanged.
- **AC-9 (TTL skip).** Same bundle immediately after: second
  `load_statement_set` makes **zero** `Company` and `get_filings` calls
  (`_sec.company.assert_not_called()` after reset), returns the same
  `StatementSet`, and updates `last_accessed` in the LRU index.
- **AC-10 (TTL expiry).** With `checked_at` backdated beyond the TTL (or the
  clock advanced), the next call does one `Company` + `get_filings` and writes
  a newer `checked_at`.
- **AC-11 (TTL 0).** With TTL 0 every call revalidates (counts equal call
  count), preserving the old behaviour.
- **AC-12 (newer filing inside TTL window).** A newer filing on SEC is *not*
  noticed until the TTL expires (documented trade-off); once expired it
  rebuilds (`from_filings` called once) and the new bundle's `checked_at` is
  fresh. A forced schema bump or corrupt file inside the window rebuilds
  immediately regardless of `checked_at` (R4).
- **AC-13 (quarterly).** The quarterly stale path records one `checked_at`
  after two `get_filings` calls (10-Q and 10-K), and the TTL skip avoids both.
- **AC-14 (offline fallback, the existing test).**
  `test_stale_bundle_is_served_when_sec_is_unreachable` passes: stale
  bundle served, WARNING logged, `from_filings` not called, cold cache still
  raises `ConnectionError`. Added assertion: `checked_at` is **not** written
  after the failed check, and a following call retries SEC.
- **AC-15 (rebuild failure is not masked).** SEC shows a newer filing, then
  `XBRLS.from_filings` raises: the error propagates; the stale bundle is
  neither served nor modified.
- **AC-16 (missing/future `checked_at`).** `checked_at` in the future triggers
  a check (R4).
- **AC-17 (fresh bundles unchanged).** A fresh bundle is served with no SEC
  access and no meta write (`meta.json` mtime unchanged).
- **AC-18 (report).** `calc_residual_report` on a stale bundle with and
  without `checked_at` produces the same residual frame, with no network
  access and no meta change.

`ruff check .` and `ruff format --check .` pass; existing tests pass except
the intentional `_seed_cache`/assert updates above.

## 8. Risks

- **R1. Newer filings are noticed up to one TTL late.** Accepted: the bundle is
  already months old by definition, a day is negligible, and TTL 0 is the
  escape hatch. Set expectations in the config comment.
- **R2. Stale meta clobbering a rebuilt bundle.** The touch is a
  read-modify-write of `meta.json`; without the R6 `expected_latest_filing_date`
  guard a slow request could overwrite a concurrent rebuild's meta with the
  old date, making the new frames look like the old build (and re-triggering a
  rebuild). The guard shrinks but does not eliminate the window: the check and
  replace are not atomic without a lock.
- **R3. Overlap with the concurrency spec.** Both change meta writes. If that
  spec lands first, `touch_period_bundle_checked` must (a) take the per-bundle
  lock around read-modify-replace, (b) compare `bundle_id` as well as
  `latest_filing_date` (if bundle_id changed, return `False`), and (c) use the
  unique-temp-name rule (R10 there). Its `save_period_bundle` swap and
  `bundle_id` rotation already give new bundles a fresh `checked_at` for free.
  If this lands first, the unique temp name and guard above are the bridge;
  the concurrency work wraps this function with the lock. Lock order stays
  `index lock` → `bundle lock`; this function takes only the bundle lock and
  never the index lock (`_touch` is a separate call).
- **R4. Single-flight.** Under concurrent stale requests that are all past the
  TTL, today's code lets each hit SEC. The concurrency spec's build lock
  does not cover the freshness check (it is not a build). This spec
  reduces the herd but does not remove a first-expiry burst (N requests all see
  `checked_at` expired and all check once). Acceptable for one user; a
  check-time re-read of `checked_at` under the bundle lock is the fix if needed
  (P2).
- **R5. Offline fallback masks real bugs.** A broad `except Exception` around
  the freshness check can hide a programming error as "SEC unreachable". Mitigation:
  the fallback only wraps the three SEC calls, always logs the exception at
  WARNING with its type, and does not write `checked_at`; and a failure to
  *build* still raises (R5 in §4).
- **R6. Disk writes on a read path.** A page view may now rewrite a ~200 byte
  JSON. Negligible, once per TTL, and failure-tolerant.
- **R7. Eviction/LRU drift.** Serving a stale bundle within the TTL still
  touches the LRU, so recency is unaffected.
- **R8. TTL applies after a clock change.** A wall-clock jump back makes
  `checked_at` look future → revalidate (safe). A jump forward expires early
  (one extra check). Both safe.

## 9. Suggested implementation order

1. `config.py`: `EDGARTOOLS_REVALIDATE_TTL_HOURS`.
2. `cache.py`: `is_recheck_due`, `checked_at` parse in `read_period_bundle` and
   `CachedStatementSet`, `save_period_bundle` writes it. Tests AC-4..AC-6.
3. `cache.py`: `touch_period_bundle_checked` with guard and unique temp name.
   Tests AC-1..AC-3, AC-7.
4. `source.py`: record the check (AC-8), TTL skip (AC-9..AC-13, AC-16..AC-17).
5. `source.py`: offline fallback (AC-14, AC-15). This step alone turns the
   currently failing offline test green and is independently shippable first.
6. Report warning tweak (R10, AC-18), docs: `specs/STATE.md` §4, `cache.py` and
   `source.py` docstrings, `.env` example if one lists cache settings.
7. Run `ruff check .`, `ruff format --check .`, the full default suite.

Each step is independently shippable; step 5 has no dependency on the others.

## 10. Assumptions / open questions

Assumptions (no one was asked):

- Single user, single machine; one web process plus occasional CLI/pytest runs.
- A 24 hour delay in noticing a new filing for an already-stale bundle is
  acceptable (they file at most four times a year).
- `checked_at` records "confirmed current against SEC at this time"; it is not
  a record of when the bundle was *built* (no `built_at` is added).
- `now - checked_at >= ttl` is the due condition (boundary is due).
- `EDGARTOOLS_REVALIDATE_TTL_HOURS` in hours, integer, 0 disables skipping.
- Old bundles without `checked_at` need no migration and no schema bump.
- Any `Exception` from the freshness-check SEC calls counts as "unreachable"
  for the fallback (edgartools raises assorted types).

Open questions:

1. **(Engineering, non-blocking) Fallback exception scope.** Catch `Exception`,
   or a tuple (`OSError`, `httpx` errors, edgartools-specific)? The spec picks
   broad-with-warning; narrow it if edgartools exposes a stable network error
   type.
2. **(Engineering, non-blocking) Should a recently confirmed bundle ever count
   as non-stale?** This spec says no (staleness is unchanged); the alternative
   would fold `checked_at` into `is_period_bundle_stale`, which also changes the
   residual report's meaning.
3. **(Product, non-blocking) Negative caching when offline.** Each request while
   offline pays a connection attempt before falling back. A short failure TTL
   (P2) avoids it; skipped as unneeded complexity until it is observed to hurt.
4. **(Engineering, non-blocking) Where does the TTL skip sit relative to
   `setup_edgartools()`?** Today it is the first line of `load_statement_set`
   (needs `EDGAR_IDENTITY`). Skipping it on a TTL hit is correct and matches the
   concurrency spec's R7, but means a missing `EDGAR_IDENTITY` is no longer
   reported on served-from-cache requests. This spec accepts that; confirm.
5. **(Engineering, non-blocking) Concurrency spec ordering.** Land this first
   (smaller) and fold the locking in, or after? Either works (Risks R3).
