# Atomic, concurrency-safe edgartools cache

Status: proposed. Nothing implemented. Touches the edgartools cache
(`src/api/edgartools/cache.py`), the build path and edgartools setup in
`src/api/edgartools/source.py`, and nothing else in `src/` (the route
`src/web/routes/statements.py` is unchanged). Architecture reference:
`specs/STATE.md` §4 (EDGAR cache). Related and independent of
`specs/features/ticker-cik-pinning.md`; both rewrite `touch_company_cache`
(see Risks).

## 1. Problem

`GET /statements/{ticker}` is a sync FastAPI handler, so Starlette runs it on a
thread pool and requests overlap. The CLIs (`calc_residual_report`, the
`pytest -m data` run) can also run in another process against the same
`data/edgartools_cache/`. None of the cache code was written with overlap in
mind. Verified by reading `cache.py` and `source.py`:

**P1. `save_period_bundle` is not atomic for readers.** It calls
`delete_period_bundle` (`shutil.rmtree` of `companies/{cik}/{period}/`), then
`mkdir`, then writes six parquet files, then `meta.json` last. "meta last"
protects a reader that arrives *before* the write finishes (no meta → miss),
but not one that arrives *during* the next save of an existing bundle:

1. Reader sees `meta.json` of the old bundle (`meta_path.exists()` is true).
2. Writer's `rmtree` removes the files; reader's `pd.read_parquet` raises
   `FileNotFoundError` (an `OSError`).
3. `read_period_bundle` treats that as a corrupt bundle and calls `discard()`
   → `delete_period_bundle` → `rmtree` of the directory the writer has just
   recreated and is filling.
4. The writer's next `to_parquet` fails (`FileNotFoundError`) or, worse,
   leaves a bundle with some files missing; `meta.json` may still land. The
   request fails with a 500, and the next read re-discards the half bundle.

The same shape applies to any reader whose `discard()` runs after a writer has
started: `discard()` is an unconditional `rmtree` with no check that the
directory it is deleting is still the one that was bad. A reader can also read
a *mixed* bundle (income from the old build, balance from the new) if the swap
lands between its file reads; nothing detects this today.

**P2. `company_lru.json` read-modify-write loses updates.** `touch_company_cache`
(`_load_index` → mutate → evict → `_save_index`), `set_pinned_tickers`
(`_load_index` → replace `pinned_tickers` → `_save_index`) and the eviction
inside `touch_company_cache` are all unlocked. Two overlapping touches both
load the same index; the second save overwrites the first's entry, so a
company's bundle exists on disk but not in the index (never evicted, never
found by `find_cached_cik`, so every request pays a `Company(ticker)` SEC
lookup). A `set_pinned_tickers` racing a touch can silently drop the pins
(the exact thing the pinning spec protects). `_save_index` also writes to the
fixed name `company_lru.tmp`: two concurrent saves interleave writes into one
file, or the second `replace` raises `FileNotFoundError` because the first
already renamed it. `save_period_bundle`'s `meta.tmp` has the same fixed-name
problem for two writers of the same bundle.

**P3. `setup_edgartools()` runs on every call, and its cache cap races
downloads.** `load_statement_set` calls `setup_edgartools()` first, which calls
`_configure_edgartools_cache()`: `mkdir`, two `os.environ` writes, then
`_clear_http_cache_if_over`, which does `clear_cache(dry_run=True)` (walks the
whole `_cache`/`_tcache` tree) on *every* request, including pure cache hits
that never touch the network. When over the cap, `clear_cache(dry_run=False)`
deletes every file under those directories, including files another thread is
in the middle of downloading for a build. And because nothing coordinates
builds, two requests for the same cold company both pass the cache check, both
call `Company`, `get_filings` and `XBRLS.from_filings`, both rebuild (minutes
of SEC traffic each, against SEC's rate limit), and both `save_period_bundle`
into the same directory, which is P1 again, writer against writer.

Consequences today are intermittent 500s on `/statements/{ticker}`, a bundle
silently deleted or half-written, an index that forgets companies or pins, and
wasted SEC requests. It will get worse as soon as the wizard issues several
`load_statement_set` calls per page or a second tab is open. The single-user
app rarely hits this by accident, but `pytest -m data` plus a browser session
(or two tabs) does.

## 2. Goals

1. A reader never sees a partial or mixed bundle, and a reader can never delete
   a bundle that was healthy or that a writer is creating. Verified by thread
   tests (§7).
2. Concurrent `touch_company_cache` / `set_pinned_tickers` calls (threads and
   processes) lose no company entry and no pin.
3. Concurrent requests for the same cold `(cik, period)` build once and share
   the result; builds for different `(cik, period)` still run in parallel.
4. A pure cache hit does no edgartools setup work beyond a constant-time check
   and never touches the HTTP cache directory.
5. The HTTP cache cap can never delete files out from under a build running in
   the same process.
6. A crash mid-write leaves nothing a reader treats as a bundle, and leftovers
   are cleaned up on later runs.

## 3. Non-goals

- **No multi-host or distributed locking.** The app is personal and local; the
  cache lives on one machine's disk. Locks are same-host (threads plus
  processes via OS file locks). Network filesystems (NFS, iCloud-synced data
  dir) are not supported for concurrent use.
- **No cross-process coordination of the HTTP cache cap.** Same-process safety
  only; the residual cross-process risk is documented (Risks, R3).
- **No change to the cache layout, `CACHE_SCHEMA_VERSION` semantics, staleness
  rules, `load_statement_set`'s signature or the `Statement`/`StatementSet`
  contracts.** One additive, optional `meta.json` field (`bundle_id`) is
  introduced; old bundles remain valid without it.
- **No async rewrite** of the route or the loader, and no move to a worker
  queue or background build with a "loading" page. Waiters block (bounded by a
  timeout).
- **No new cache backend** (SQLite, DuckDB). Parquet files plus JSON stay.
- **No change to SEC rate limiting / retry policy**; that is edgartools' job.

## 4. Requirements

### P0

**R1. Atomic bundle swap.** `save_period_bundle` builds the new bundle in a
sibling temp directory `companies/{cik}/.{period}.tmp-{uuid4hex}/` (parquet
files, then `meta.json` inside it), then swaps it in under the per-bundle
lock (R3): rename any existing `{period}/` to `.{period}.old-{uuid4hex}/`,
`os.replace` the temp dir to `{period}/`, then `rmtree` the old directory
(outside the lock; failure is only a warning). The final directory is only
ever a complete bundle or absent. `delete_period_bundle` is no longer called
from inside save. (Directories cannot be `os.replace`d over a non-empty
directory on POSIX, hence the two-step; the window between the two renames
shows readers a missing bundle, which is a cache miss, not corruption; R2.)
If any write fails, the temp dir is removed and the existing bundle is left
untouched.

**R2. Reads never destroy healthy data.**
- `meta.json` gains `bundle_id` (uuid4 hex, new per save). `read_period_bundle`
  reads meta, reads all files, re-reads meta, and retries (up to 3 times,
  short sleep) when `bundle_id` changed or a file is missing. A bundle without
  `bundle_id` (written before this feature) is read as before, with one
  retry on missing file.
- A read that still fails after retries does **not** discard directly. It
  takes the per-bundle lock (R3), re-reads once under the lock (no writer can
  be mid-swap), and only if the bundle is still invalid under the lock does it
  delete it. `FileNotFoundError` on the first look with a changed or vanished
  directory returns `None` (miss) without deleting anything.
- `discard()` (`delete_period_bundle` on the prune path, schema mismatch,
  stale-in-`load_period_bundle`) always runs under the per-bundle lock and
  rechecks that the directory it is removing still has the `bundle_id` (or the
  mtime and meta contents) that was judged bad.
- `prune=False` callers (reports) take no lock, delete nothing, and apply the
  same retry on a changed `bundle_id`.

**R3. Per-bundle file lock.** One lock file per `(cik, period)` at
`{cache_dir}/.locks/bundle-{cik}-{period}.lock`, via the `filelock` package
(`FileLock`; works across threads, which hold separate file descriptors, and
across processes). Held for: the swap in R1, a discard, and a verification
re-read (R2). Never held while building statements from SEC or while writing
parquet (the writes go to the private temp directory first), so readers
and waiters block for milliseconds.

**R4. Index lock and atomic index writes.** One lock file
`{cache_dir}/.locks/company_lru.lock`. `touch_company_cache` and
`set_pinned_tickers` run `load → mutate → (evict) → save` entirely under it.
`_save_index` writes to a unique temp file in the same directory
(`company_lru.json.{uuid4hex}.tmp`), `fsync`s, `os.replace`s, and removes its
temp file on error. Read-only index accessors (`_load_index` as used by
`pinned_tickers`, `find_cached_cik`, `cached_companies`) stay lock-free: the
file is only ever replaced whole, so they see either the old or the new index.
A corrupt index is still treated as empty, but when that happens inside a
locked write the corrupt file is first copied to `company_lru.json.corrupt`
so a pin list is not silently lost.

**R5. Lock ordering (no deadlocks).** Order is: `index lock` → `bundle lock`.
Code holding a bundle lock must never take the index lock.
`save_period_bundle` therefore does not touch the index (it already doesn't;
`source.py` calls `_touch` after it returns), and eviction (which holds the
index lock) acquires bundle locks only for the evicted CIK's periods, and
never the reverse. Every lock acquisition has a timeout (default 60 s for
index/bundle locks) that raises a clear `CacheLockTimeout` rather than
hanging a worker thread.

**R6. Atomic company eviction.** `_evict_company` renames
`companies/{cik}/` to `companies/.trash-{cik}-{uuid4hex}` (under the index
lock plus that CIK's bundle locks), then `rmtree`s the renamed directory
outside the locks. Readers mid-read get a miss, never a half-deleted tree.
`.trash-*`, `.*.tmp-*`, `.*.old-*` names are ignored by every reader and by
`companies/` scans.

**R7. Configure edgartools once.** Split `setup_edgartools()` in
`source.py`:
- `setup_edgartools()` keeps its public contract (load `.env`, require
  `EDGAR_IDENTITY`, configure) but the configuration (`mkdir`, the two
  `os.environ` writes) runs at most once per process behind a module-level
  `threading.Lock` and a `_configured` flag. The `EDGAR_IDENTITY` check stays
  per call (a dictionary lookup).
- `load_statement_set` does **not** call `setup_edgartools()` on the cache-hit
  path unless it needs `Company` (network). A fully cached, fresh bundle is
  served without importing/touching edgartools state. (`find_cached_cik` +
  `read_period_bundle` + `_serve_cached` need none of it.)
- The HTTP cache size check (`_clear_http_cache_if_over`) moves out of
  configuration into the build path only (R8).

**R8. HTTP cache cap is build-gated.** A module-level gate in `source.py`
(`threading.Condition` plus an `active_builds` counter): builds increment the
counter on entry and decrement on exit; the size check/clear runs only at the
start of a build, only when `active_builds == 0` (other builds wait for the
clear to finish before they start), and never while any build in this process
is running. The size check at most once per `EDGARTOOLS_HTTP_CACHE_CHECK_SECONDS`
(default 600) per process so a burst of cold builds does not walk the tree
repeatedly. Cache hits never reach it.

**R9. Single-flight builds per `(cik, period)`.** After resolving the CIK
(`find_cached_cik` hit or `Company(ticker).cik`), the build path acquires a
build lock for `(cik, period)` (file lock `{cache_dir}/.locks/build-{cik}-{period}.lock`,
so it also serializes the CLI against the server; distinct from the bundle
lock of R3, which is short-lived). Inside it, it **re-reads the cache**
(double-checked): if a fresh bundle appeared while it waited, it serves that
and does not build. Only the lock holder runs `company.get_filings`,
`XBRLS.from_filings`, the statement loop and `save_period_bundle`.
Builds for different `(cik, period)` do not block each other. Lock order for
this: `build lock` → (`bundle lock` inside `save_period_bundle`) → release
build lock → `_touch` (index lock). Build-lock wait timeout default 15 minutes
(builds take minutes), configurable; on timeout raise `CacheLockTimeout`
(surfaces as a 500 with a clear message today; mapping to 503 is P1).

**R10. Unique temp names everywhere.** No fixed `*.tmp` filename remains in
`cache.py` (`company_lru.tmp`, `meta.tmp`). Temp names carry a uuid4 hex.

### P1

**R11. Stale temp sweep.** On first use of a cache dir per process (inside the
index lock), delete `.{period}.tmp-*`, `.{period}.old-*` and `.trash-*`
entries under `companies/` and `company_lru.json.*.tmp` older than one hour
(by mtime). Younger ones are left (they may belong to a live writer in another
process).

**R12. Lock files are self-contained.** `.locks/` is created on demand,
ignored by `git`/eviction scans, and lock files are never deleted while held
(stale files are harmless; they are not removed on eviction).

**R13. Observability.** Log at INFO when a request waits on a build lock held
by another build, when a read retries, and when a build is skipped because
another build already produced the bundle; log at WARNING on lock timeouts.

**R14. Route-level error mapping.** `CacheLockTimeout` → HTTP 503 with a short
message in `statements.py` (the only route-side change; optional, hence P1).

### P2 (design must not preclude)

- Reader/writer sharing via versioned bundle directories plus a pointer file
  (design B below) if readers ever need strictly zero-wait reads.
- Background refresh of stale bundles while serving the stale one.
- A cross-process HTTP cache gate if a second long-lived process (a worker)
  ever builds alongside the web server.

## 5. Design options

### Atomic bundle publish

**A. Temp dir plus rename-swap under a per-bundle lock (recommended).** Write
the whole bundle privately, then take the lock for the two renames. Layout
and every reader function stay the same. Pros: no layout change, no reader
cost on the happy path (no lock), crash-safe (a half-written temp dir is never
a bundle). Cons: a microsecond window where `{period}/` is absent (a miss →
at worst a redundant rebuild; with R9's double check that rebuild finds the
new bundle); readers rely on the `bundle_id` check to detect a swap between
file reads.

**B. Versioned dirs plus a `CURRENT` pointer.** Each save writes
`{period}/v-<uuid>/` and atomically replaces a pointer file; readers resolve
the pointer once and read only that version. Pros: readers see a perfectly
consistent snapshot with no retry and no absent window. Cons: a layout change
(`CACHE_SCHEMA_VERSION` bump or dual-path reading), garbage collection of
old versions that readers might still be reading (needs refcounts or a
grace-period sweep), more code than the problem justifies for one user.

**C. Reader-writer lock around everything.** Simple to reason about but
`filelock` has no shared mode, so readers would serialize against each other,
and readers would hold a lock while reading six parquet files. Rejected for
cost and complexity.

Recommendation: **A**, with the `bundle_id` re-check for mixed-read detection.
B stays a P2 if retries prove noisy.

### Locking mechanism

**L1. `filelock` package (recommended).** Cross-thread and cross-process on one
host, tiny API, timeouts. It is already importable in the project venv
(version 3.32.2, a transitive dependency); this feature declares it as a
direct dependency in `pyproject.toml` so it cannot disappear.
**L2. `fcntl.flock` directly.** No dependency, but POSIX-only and we'd
re-implement timeouts and thread behavior. Acceptable only if adding the
dependency is unwanted; the project is already macOS/Linux-only in practice.
**L3. In-process `threading.Lock` only.** Fixes the server's thread-pool case
but not the CLI-versus-server case (which is the real data-test scenario).
Rejected, but in-process dedupe of lock objects is still done by `filelock`
itself. Recommendation: **L1**.

### Single-flight

**S1. File lock per `(cik, period)` plus double-checked cache read
(recommended).** Same mechanism for threads and processes, no registry of
futures to leak.
**S2. In-process `dict[(cik, period), Future]` registry.** Waiters share the
leader's *result object* without re-reading from disk, and it is immune to
filesystem lock oddities. But it does not protect against a second process,
and failure handling (leader error → every waiter errors vs. one retries)
needs care. Possible later layering on top of S1 if the disk re-read matters.
Recommendation: **S1**.

### HTTP cache cap

**H1. Build-path check, build-gated, rate-limited (recommended)** (R7/R8).
**H2. Check once at process start** (FastAPI startup / CLI main). No race with
in-flight builds at all, but the cap is only enforced on restart, and the
server can run for days. Could be combined with H1 as the "clear only when
no build is active" fallback.
**H3. Drop the cap and rely on edgartools' own cache management.** Depends on
the open question about where edgartools writes (below).

## 6. Affected code

| Where | Change |
| --- | --- |
| `src/api/edgartools/cache.py` `save_period_bundle` | Temp dir build, `bundle_id` in meta, swap under bundle lock; unique temp names |
| `read_period_bundle`, `delete_period_bundle`, `load_period_bundle` | Retry on `bundle_id` change; discard only under the lock after re-verify; `FileNotFoundError` on a vanished dir is a miss |
| `_save_index`, `touch_company_cache`, `set_pinned_tickers`, `_evict_company` | Index lock, unique temp file, fsync, rename-to-trash eviction, corrupt-index backup |
| new private helpers in `cache.py` | `_bundle_lock(cache_dir, cik, period)`, `_index_lock(cache_dir)`, `build_lock(...)` (public: `source.py` imports it, so no leading underscore, per STATE.md §3), `CacheLockTimeout`, `_sweep_stale_temp` |
| `src/api/edgartools/source.py` `setup_edgartools`, `_configure_edgartools_cache` | Configure once; size check removed from configuration |
| `_clear_http_cache_if_over` | Called only from the build path, behind the build gate and rate limit |
| `load_statement_set` | No setup on pure cache hits; build lock plus re-read before building; build gate counter around the build |
| `src/api/edgartools/__init__.py` | Export `CacheLockTimeout` if the route maps it (P1) |
| `src/config.py` | `EDGARTOOLS_LOCK_TIMEOUT_SECONDS` (60), `EDGARTOOLS_BUILD_LOCK_TIMEOUT_SECONDS` (900), `EDGARTOOLS_HTTP_CACHE_CHECK_SECONDS` (600); config lives only here |
| `pyproject.toml` | Declare `filelock` |
| `src/web/routes/statements.py` | P1 only: map `CacheLockTimeout` → 503 |
| `tests/test_edgartools_cache.py`, `tests/test_edgartools_source.py` | New tests (§7); existing tests keep passing unchanged |
| `specs/STATE.md`, `cache.py` module docstring | Doc update: locking model, `bundle_id`, `.locks/`, build-path-only size check |

`src/pipelines/calc_residual_report.py` needs no change (`prune=False`,
lock-free reads). The pinning spec's index schema change composes with this
(it only changes what is inside the locked critical section).

## 7. Acceptance criteria / test cases

All with real threads and `tmp_path`; no network; small synthetic frames. Tests
use `threading.Barrier` / `Event` for determinism, with a hard per-test
timeout so a regression hangs for seconds, not forever. Source-level tests
monkeypatch `Company`, `XBRLS`, `_build_statement` and `clear_cache`
(patterns already used in `tests/test_edgartools_source.py`).

**Bundle atomicity (R1–R3, R6)**

- **AC-1 (the bug, deterministic).** Save bundle v1. Patch `pd.read_parquet` so
  the first call in thread R blocks on an Event after `meta.json` was read.
  Thread W calls `save_period_bundle` with v2 and completes. Release R. Then:
  R returns v2 or `None`, never raises, the directory still holds v2 with a
  valid meta, W raised nothing, and a following `read_period_bundle` returns
  v2. (Regression of the discard-deletes-writer's-dir bug.)
- **AC-2 (no mixed reads).** Each generation `g` stores `g` in every frame and
  calc-edge cell of all three statements. One writer saves generations 1..50
  continuously; 8 reader threads call `read_period_bundle` 200 times each.
  Assert: no exception, and every returned bundle has a single generation
  across all six frames. After the first save, `None` is allowed only during
  the brief swap window; assert it is never followed by the directory being
  deleted (final read returns generation 50).
- **AC-3 (failed write keeps the old bundle).** Patch `to_parquet` to raise on
  the 4th file. `save_period_bundle` raises; the previous bundle is still
  readable and equal to the old content; no `.tmp-*` directory remains.
- **AC-4 (crash leftovers are invisible).** Create `.annual.tmp-dead/` with
  partial files and no meta; `read_period_bundle` returns the real bundle (or
  `None`), never the temp. The R11 sweep removes it once older than 1 hour and
  leaves a fresh one.
- **AC-5 (real corruption is still discarded).** Truncate a parquet file in a
  stored bundle with no writer active: read returns `None` and the directory
  is deleted (existing behaviour preserved), including after retries.
- **AC-6 (concurrent same-bundle writers).** 6 threads `save_period_bundle`
  the same `(cik, period)` with different generations. No exception; the final
  directory is exactly one of the generations, complete and self-consistent;
  no temp or old dir remains.
- **AC-7 (eviction during read).** Reader blocked mid-read on a company that
  `touch_company_cache` then evicts: reader returns `None` or the full bundle
  (it started before the swap), raises nothing; the trash directory is gone
  afterward.
- **AC-8 (legacy meta).** A bundle written without `bundle_id` still reads
  fine and is not rebuilt.
- **AC-9 (`prune=False`).** With a writer mid-swap, `prune=False` reads never
  delete anything and never raise.

**Index (R4, R5, R10)**

- **AC-10 (no lost touches).** 16 threads, each `touch_company_cache` for a
  distinct CIK, `max_companies=100`, started on a barrier. Afterwards all 16
  CIKs are in the index and `cached_companies` returns all of them.
- **AC-11 (pins survive touches).** One thread loops `set_pinned_tickers`
  with a growing list while 8 threads touch; the final index has the last
  pin list *and* all touched companies. Eviction never removes a pinned
  company in the interleaving.
- **AC-12 (unique temp files).** While 16 threads run `_save_index`
  concurrently, no `FileNotFoundError`; no `company_lru.*.tmp` remains; the
  JSON file is always parseable (a reader thread loads it in a tight loop and
  never sees a corrupt-file warning, checked with `caplog`).
- **AC-13 (cross-process).** Same as AC-10 with `multiprocessing` (spawn), 4
  processes × 8 touches each. All 32 entries present. Marked slow, in the
  default suite only if under ~5 s.
- **AC-14 (corrupt index backup).** A corrupt `company_lru.json` followed by a
  locked write leaves `company_lru.json.corrupt` holding the original bytes.
- **AC-15 (no deadlock).** A stress test combining `touch_company_cache` (with
  eviction), `save_period_bundle`, and `read_period_bundle(prune=True)` on
  the same CIKs from 12 threads finishes within 30 s with no exception;
  lock timeouts patched to 5 s turn any deadlock into a failure, not a hang.

**Single-flight and setup (R7–R9)**

- **AC-16 (single flight).** Monkeypatch `Company` (fixed CIK), `get_filings`,
  `XBRLS.from_filings` and `_build_statement` with a counter and
  `time.sleep(0.3)`. 8 threads call `load_statement_set("AAPL", "annual")` on
  a cold cache. Build counter == 1; all 8 return equal `StatementSet`s;
  exactly one `save_period_bundle`; every thread's request completed.
- **AC-17 (different keys run in parallel).** Two builds for different CIKs
  (and the same CIK, annual vs. quarterly) rendezvous on a
  `Barrier(2, timeout=5)` inside the patched builder; both pass (they are not
  serialized by one global lock).
- **AC-18 (leader failure).** The leader's build raises; waiters do not hang:
  one waiter takes over the lock and builds (counter 2), the rest are served
  from its result. A test where every attempt raises ends with all threads
  receiving the error.
- **AC-19 (stale-bundle path).** Stale bundle plus 4 concurrent requests and a
  newer filing: one rebuild; the rest serve the rebuilt bundle. With no newer
  filing: zero builds, all serve the stale bundle, one `get_filings` at most
  per request but no `XBRLS` call.
- **AC-20 (cache hit does no setup).** Preload a fresh bundle and index. Patch
  `_configure_edgartools_cache` and `clear_cache` with counters. 50 concurrent
  `load_statement_set` calls: `clear_cache` is called 0 times and
  `_configure_edgartools_cache` 0 times; `Company` is never called.
- **AC-21 (configure once).** 20 concurrent cold calls: `_configure_edgartools_cache`
  runs exactly once; `EDGAR_IDENTITY` missing still raises `ValueError` on
  every call.
- **AC-22 (cap never races a build).** Thread A is inside a patched build
  blocked on an Event. With `clear_cache(dry_run=True)` reporting over-cap,
  thread B starts a different build: `clear_cache(dry_run=False)` has not
  been called while A is active. Release A; B's clear then runs before B's
  build proceeds, and `clear_cache` was called at most once per
  `EDGARTOOLS_HTTP_CACHE_CHECK_SECONDS` window (patch the clock).
- **AC-23 (lock timeout).** Hold a bundle lock in the test thread with the
  timeout patched to 0.2 s: `read_period_bundle`'s verification path raises
  `CacheLockTimeout`, quickly, and deletes nothing.

Existing tests in `tests/test_edgartools_cache.py` and
`tests/test_edgartools_source.py` pass unchanged; `ruff check` and `ruff
format --check` pass.

## 8. Risks

- **R1. Windows / non-POSIX.** The rename-swap and `filelock` behave differently
  (open files block deletion). The project is run on macOS; Windows is not a
  target. Stated as an assumption.
- **R2. Lock files on odd filesystems.** `flock` is unreliable on some network
  and cloud-synced folders. Documented as unsupported (non-goal); a timeout
  turns a broken lock into an error, not a hang.
- **R3. Cross-process HTTP cap race remains.** If the CLI and the server both
  build and one runs `clear_cache(dry_run=False)`, it can delete a file the
  other is writing. edgartools will refetch or fail that one request; a retry
  succeeds. Acceptable for a personal app; the P2 cross-process gate is the
  fix if it shows up.
- **R4. Builds hold a request thread for minutes.** Waiters on the build lock
  occupy workers of the default (40-thread) pool. With one user this is fine;
  the timeout bounds it. A "building" interstitial is a future UX concern.
- **R5. Merge overlap with the pinning spec.** Both rewrite
  `touch_company_cache`, `_save_index` and the index schema. They are
  independent in behaviour; implementing locks first (smaller diff) and
  pinning second means the pinning migration automatically runs inside the
  locked section. If pinning lands first, this change wraps its code with the
  lock.
- **R6. Retry loop masks real bugs.** Retries are capped (3) and logged at
  INFO; real corruption still ends in a verified discard (AC-5).
- **R7. Extra disk during save.** Old and new bundle coexist briefly (each is a
  few MB of parquet). Negligible.
- **R8. `bundle_id` re-read cost.** One extra tiny JSON read per cache hit.
  Negligible next to six parquet reads.
- **R9. Lock leakage.** A killed process releases its `flock` automatically
  (kernel-held), so no stale-lock cleanup is needed; leftover empty `.lock`
  files are harmless.

## 9. Suggested implementation order

1. Add `filelock` to `pyproject.toml`, the three config tunables, `CacheLockTimeout`
   and the lock helpers in `cache.py`. No behaviour change yet.
2. Index: lock `touch_company_cache` / `set_pinned_tickers`, unique temp name,
   fsync, corrupt-file backup. Tests AC-10..AC-15 (AC-15 once step 3 exists).
3. Bundle: temp-dir build plus swap in `save_period_bundle`, `bundle_id`,
   unique meta temp. Tests AC-3, AC-4, AC-6, AC-8.
4. Reads: retry on `bundle_id`, discard only under lock after re-verify,
   trash-rename eviction. Tests AC-1, AC-2, AC-5, AC-7, AC-9, AC-23.
5. `source.py`: configure-once, no setup on pure hits, build-path-only
   gated size check. Tests AC-20..AC-22.
6. `source.py`: build lock, double-checked read, single-flight. Tests
   AC-16..AC-19.
7. Stale temp sweep (R11), logging (R13), optional 503 mapping (R14).
8. Docs: `specs/STATE.md` §4 (locking model, `bundle_id`, `.locks/`,
   size-check placement) and the `cache.py` docstring. Run the AC-15 stress
   test and `ruff` before committing.

Each step is independently shippable; steps 2–4 close P1/P2, 5–6 close P3.

## 10. Assumptions / open questions

Assumptions made (no one was asked):

- Single machine, POSIX (macOS/Linux), local disk; one web server process plus
  occasional CLI/pytest processes.
- `filelock` is acceptable as a declared dependency.
- A short read miss during the swap is acceptable (it leads to at worst one
  redundant cache re-check, never a wrong result).
- Waiting up to minutes for another request's build is preferable to a
  duplicate build; failing with a timeout error after 15 minutes is acceptable.
- No schema bump: `bundle_id` is an optional field; old bundles remain valid.
- Request volume is a handful of concurrent requests, so a coarse design is
  adequate.

Open questions:

1. **(Blocking for R8/H1; engineering) Where does edgartools write its HTTP
   cache now, and does `clear_cache` measure that directory?** Commit
   `f608029` removed the code that replaced edgartools' `HTTP_MGR` with a
   client cached under `EDGARTOOLS_CACHE_DIR`. What remains is only
   `os.environ["EDGAR_LOCAL_DATA_DIR"] = EDGARTOOLS_CACHE_DIR` and
   `_clear_http_cache_if_over`, whose docs claim it clears the `_cache` /
   `_tcache` directories under `EDGAR_LOCAL_DATA_DIR`. If edgartools' own HTTP
   manager caches elsewhere (its default `~/.edgar/_cache`, or a path fixed
   when `edgar` was imported, before our env var was set), then the cap now
   measures a different directory (likely always under the cap, so a silent
   no-op) while the real cache grows unbounded, or `clear_cache` is wiping
   a different directory than the one being written. Also: are `EDGAR_LOCAL_DATA_DIR`
   and the allow-network flag read at import time or at call time? If at import
   time, "configure once" must happen before the first edgartools use and
   setting the variable in `setup_edgartools()` after `from edgar import ...`
   is already too late. Needs a one-off check (print edgartools' resolved
   cache dir and `clear_cache(dry_run=True)` result after `setup_edgartools()`),
   and STATE.md §4's description updated to whatever is true. The answer
   decides between H1 (keep and fix), H2, and H3 (drop the cap).
2. **(Engineering) Is `clear_cache` thread-safe against edgartools' own
   in-flight HTTP writes?** If edgartools writes through temp files, a
   concurrent clear only costs a refetch; if not, the gate in R8 is more
   important than assumed. Also whether edgartools itself is safe to call
   from several threads (shared `HTTP_MGR`, shared rate limiter): this spec
   makes our cache safe, not edgartools.
3. **(Engineering, non-blocking) Does `Company(ticker)` need to run before the
   build lock?** It is needed to learn the CIK on a cold cache (one SEC
   lookup per concurrent request), which single-flight does not dedupe. Likely
   acceptable (it is cheap and edgartools caches it); a ticker-level lock
   would also dedupe it, at the cost of one more lock.
4. **(Engineering, non-blocking) Timeout defaults** (60 s locks, 15 min build
   lock) and whether a timeout should be a 503 or just a 500 for now.
5. **(Engineering, non-blocking) Is the bundle swap "rename-old, rename-new"
   window acceptable?** If a strict zero-miss window is wanted, option B
   (versioned dirs) is the answer; this spec judges it not worth the layout
   change.
6. **(Product, non-blocking) Should a request for a cold company that is
   already building show a "building, retry" page** instead of blocking? This
   spec keeps blocking (non-goal) because the UI is deliberately simple.
7. **(Engineering, non-blocking) `pytest -m data` and the server together.**
   Is concurrent use during the data test a supported workflow, or do we just
   want the guarantees so it does not corrupt anything? This spec assumes
   "guarantees, not performance".
