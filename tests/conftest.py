"""Pytest fixtures shared across tests, and the data-test ticker harness.

A test that takes ``data_ticker`` is a data test: it runs once per ticker in
the selected gitignored list, one ticker per line, ``#`` comments.
``DATA_TICKERS`` picks the list (``short``, the default, or ``long``). A
missing prerequisite skips the test, or fails it when ``REQUIRE_DATA_TESTS=1``
(``make test`` sets it).
"""

import functools
import os
from pathlib import Path

import pytest

import src.api.edgartools.cache as cache_mod
from src.config import load_project_dotenv

TESTS_DIR = Path(__file__).parent
DATA_TICKER_LISTS = {
    "short": TESTS_DIR / "data_test_tickers.txt",
    "long": TESTS_DIR / "data_test_tickers_long.txt",
}
_LINK_HINT = "in a worktree, run python3 scripts/link_worktree_files.py"


def _selected_list() -> Path:
    selection = os.environ.get("DATA_TICKERS", "short")
    if selection not in DATA_TICKER_LISTS:
        raise pytest.UsageError(
            f"DATA_TICKERS={selection!r}; use one of {sorted(DATA_TICKER_LISTS)}"
        )
    return DATA_TICKER_LISTS[selection]


@functools.cache
def _list_tickers(path: Path) -> tuple[str, ...]:
    if not path.exists():
        return ()
    lines = path.read_text(encoding="utf-8").splitlines()
    tickers = (line.split("#", 1)[0].strip().upper() for line in lines)
    return tuple(t for t in tickers if t)


def _missing_prerequisite(path: Path) -> str | None:
    rel = path.relative_to(TESTS_DIR.parent)
    if not path.exists():
        return f"{rel} is missing: create it with one ticker per line ({_LINK_HINT})"
    if not _list_tickers(path):
        return f"{rel} lists no tickers: add one ticker per line"
    load_project_dotenv()
    if not os.environ.get("EDGAR_IDENTITY"):
        return f"EDGAR_IDENTITY is not set: add it to .env ({_LINK_HINT})"
    return None


@functools.cache
def _pin_data_tickers(path: Path) -> None:
    # Added to the user's pins, not replacing them: pinned test companies
    # never evict the user's companies from the LRU.
    cache_mod.add_pinned_tickers(_list_tickers(path))


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "data_ticker" not in metafunc.fixturenames:
        return
    tickers = _list_tickers(_selected_list())
    metafunc.parametrize(
        "data_ticker",
        tickers or [None],
        ids=list(tickers) or ["no-data-tickers"],
        indirect=True,
    )


@pytest.fixture
def data_ticker(request: pytest.FixtureRequest) -> str:
    path = _selected_list()
    problem = _missing_prerequisite(path)
    if problem:
        if os.environ.get("REQUIRE_DATA_TESTS") == "1":
            pytest.fail(f"REQUIRE_DATA_TESTS=1 and {problem}", pytrace=False)
        pytest.skip(problem)
    _pin_data_tickers(path)
    return request.param


@pytest.fixture
def use_cache_dir(monkeypatch: pytest.MonkeyPatch):
    """Point ``touch_company_cache`` (which takes no cache_dir) at a directory.

    Returns ``use(cache_dir, size=10)``; patches the cache module's
    ``EDGARTOOLS_CACHE_DIR`` / ``EDGARTOOLS_COMPANY_CACHE_SIZE`` globals.
    """

    def use(cache_dir, size: int = 10):
        monkeypatch.setattr(cache_mod, "EDGARTOOLS_CACHE_DIR", cache_dir)
        monkeypatch.setattr(cache_mod, "EDGARTOOLS_COMPANY_CACHE_SIZE", size)
        return cache_dir

    return use
