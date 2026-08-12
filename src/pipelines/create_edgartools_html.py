"""Pipeline: fetch SEC statements via edgartools and write a standalone HTML viewer."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from src.api.edgartools.source import get_statement_views
from src.config import PROCESSED_DATA_DIR
from src.models.edgartools.html_renderer import render_statement_html

logger = logging.getLogger(__name__)


def create_edgartools_html(
    ticker: str,
    statement_type: str,
    period: str,
    num_periods: int = 10,
    output_path: Path | None = None,
) -> Path:
    views = get_statement_views(ticker, statement_type, period, num_periods)
    return render_statement_html(
        views,
        ticker=ticker,
        statement_type=statement_type,
        period=period,
        output_path=output_path,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a standalone HTML financial statement viewer from SEC EDGAR data.",
    )
    parser.add_argument("ticker", help="Stock ticker symbol (e.g. AAPL)")
    parser.add_argument(
        "--statement-type",
        choices=["income", "balance", "cashflow"],
        default="income",
        help="Statement to render (default: income)",
    )
    parser.add_argument(
        "--period",
        choices=["annual", "quarterly"],
        default="annual",
        help="Annual (10-K) or quarterly (10-Q) filings (default: annual)",
    )
    parser.add_argument(
        "--num-periods",
        type=int,
        default=10,
        help="Maximum number of periods to include (default: 10)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=f"Output HTML path (default: {PROCESSED_DATA_DIR}/<ticker>_<statement>_<period>.html)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    args = parser.parse_args()
    logging.basicConfig(level=args.log_level, format="%(levelname)s: %(name)s: %(message)s")

    output = create_edgartools_html(
        args.ticker.upper(),
        args.statement_type,
        args.period,
        args.num_periods,
        args.output,
    )
    logger.info("Wrote %s", output)


if __name__ == "__main__":
    main()
