"""Data test over real SEC filings: calc residuals of the test tickers.

Run with ``pytest -m data`` (the default ``pytest`` run deselects it). Needs
``EDGAR_IDENTITY`` in ``.env``.

The tickers come from ``tests/data_test_tickers.txt`` (gitignored, so edit it
freely): one ticker per line, ``#`` starts a comment. Without the file the
test is skipped. The tickers are pinned in the company LRU, so they are never
evicted and never evict user companies; bundles are loaded through
``load_statement_set`` into the app's own cache (stale ones are rebuilt from
SEC), so a later request for one of them is already cached.

The check is the calc-residual report's residuals over those statement sets:
every calc parent must equal ``Σ weight·child`` in every period. Residuals are
computed from what ``load_statement_set`` returns rather than with
``collect_residuals``, which re-reads the cache and skips bundles that are
already stale by their latest filing date (e.g. a company between a 10-K and
its next 10-Q).
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from src.api.edgartools.cache import set_pinned_tickers
from src.api.edgartools.source import load_statement_set
from src.config import load_project_dotenv
from src.models.calc_residuals import calc_residuals
from src.models.statement import STATEMENT_TYPES
from src.pipelines.calc_residual_report import (
    DEFAULT_TOLERANCE,
    PERIOD_TYPES,
    non_zero_residuals,
)

TICKERS_FILE = Path(__file__).parent / "data_test_tickers.txt"

# Cap on residual rows printed in a failure message.
_MAX_REPORTED = 40


def _test_tickers() -> list[str]:
    tickers = []
    for line in TICKERS_FILE.read_text(encoding="utf-8").splitlines():
        ticker = line.split("#", 1)[0].strip().upper()
        if ticker:
            tickers.append(ticker)
    return tickers


@pytest.mark.data
def test_test_tickers_have_no_calc_residuals() -> None:
    load_project_dotenv()
    if not os.environ.get("EDGAR_IDENTITY"):
        pytest.skip("EDGAR_IDENTITY is not set (add it to .env)")
    if not TICKERS_FILE.exists():
        pytest.skip(f"No test tickers: create {TICKERS_FILE} (one ticker per line)")
    tickers = _test_tickers()
    if not tickers:
        pytest.skip(f"{TICKERS_FILE} lists no tickers")

    # Pin before loading so test companies never evict user companies.
    set_pinned_tickers(tickers)
    frames = []
    for ticker in tickers:
        for period in PERIOD_TYPES:
            statements = load_statement_set(ticker, period)
            for statement_type in STATEMENT_TYPES:
                frame = calc_residuals(statements.get(statement_type))
                frame.insert(0, "statement", statement_type)
                frame.insert(0, "period_type", period)
                frame.insert(0, "ticker", ticker)
                frames.append(frame)
    residuals = pd.concat(frames, ignore_index=True)

    non_zero = non_zero_residuals(residuals, DEFAULT_TOLERANCE)
    columns = [
        "ticker",
        "period_type",
        "statement",
        "row_id",
        "period",
        "reported",
        "computed",
        "residual",
    ]
    assert non_zero.empty, (
        f"{len(non_zero)} of {len(residuals)} parent × period calc residuals "
        f"exceed {DEFAULT_TOLERANCE} (largest relative first):\n"
        + non_zero[columns].head(_MAX_REPORTED).to_string(index=False)
    )
