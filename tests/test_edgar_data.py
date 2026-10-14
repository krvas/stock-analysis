"""Data test over real SEC filings: calc residuals of the test tickers.

Run with ``pytest -m data`` (the default ``pytest`` run deselects it); the
``data_ticker`` harness in ``tests/conftest.py`` picks the tickers and pins
them. Bundles are loaded through ``load_statement_set`` into the app's own
cache (stale ones are rebuilt from SEC), so a later request for one of them is
already cached.

The check is the calc-residual report's residuals over those statement sets:
every calc parent must equal ``Σ weight·child`` in every period, up to the
rounding of each value to the filing's reporting precision. Residuals are
computed from what ``load_statement_set`` returns rather than with
``collect_residuals``, which re-reads the cache and skips bundles that are
already stale by their latest filing date (e.g. a company between a 10-K and
its next 10-Q).
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.api.edgartools.source import load_statement_set
from src.models.calc_residuals import tagged_residuals
from src.models.statement import STATEMENT_TYPES
from src.pipelines.calc_residual_report import (
    DEFAULT_TOLERANCE,
    PERIOD_TYPES,
    non_zero_residuals,
)

# Cap on residual rows printed in a failure message.
_MAX_REPORTED = 40


@pytest.mark.data
def test_test_tickers_have_no_calc_residuals(data_ticker: str) -> None:
    frames = []
    for period in PERIOD_TYPES:
        statements = load_statement_set(data_ticker, period)
        frames.append(
            tagged_residuals(
                {t: statements.get(t) for t in STATEMENT_TYPES},
                ticker=data_ticker,
                period_type=period,
            )
        )
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
        "rounding",
    ]
    assert non_zero.empty, (
        f"{len(non_zero)} of {len(residuals)} parent × period calc residuals "
        "exceed rounding to the filing's reporting precision "
        "(largest relative first):\n"
        + non_zero[columns].head(_MAX_REPORTED).to_string(index=False)
    )
