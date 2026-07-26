"""Pipeline: load stock data from IndianAPI into DuckDB by company name."""

from __future__ import annotations

import argparse
import logging
from typing import Sequence

from src.api import IndianAPIClient, AlphaVantageClient, FinnhubClient
from src.config import DEFAULT_DB_PATH, SCHEMA_SQL_PATH
from src.database.manager import DatabaseManager
from src.ingestion.load_to_database import DEFAULT_TABLE_ORDER, load_company_to_db

logger = logging.getLogger(__name__)


def load_from_names(names: Sequence[str], api: str) -> None:
    """Fetch all 6 tables for each stock name and upsert into DuckDB.

    This function orchestrates the pipeline without directly calling the API
    or database — it delegates to the ingestion layer which handles both.
    """
    if api == "indianapi":
        client = IndianAPIClient()
    elif api == "finnhub":
        client = FinnhubClient()
    else:
        client = AlphaVantageClient()
    db = DatabaseManager(db_path=str(DEFAULT_DB_PATH))

    try:
        db.connect()
        db.initialize_schema(schema_path=SCHEMA_SQL_PATH)

        for name in names:
            logger.info("Loading data for %s", name)
            try:
                load_company_to_db(
                    client,
                    db,
                    name,
                    tables=DEFAULT_TABLE_ORDER,
                )
                logger.info("Finished loading %s", name)
            except Exception:
                logger.exception("Failed to load %s, continuing", name)
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load stock data from IndianAPI into DuckDB.",
    )
    parser.add_argument(
        "names",
        nargs="+",
        help="One or more stock names to load (e.g. 'Oberoi Realty' 'LIC').",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO).",
    )
    parser.add_argument(
        "--api",
        default="indianapi",
        choices=["indianapi", "alphavantage", "finnhub"],
        help="Which API to fetch the stock data from"
    )

    args = parser.parse_args()
    logging.basicConfig(level=args.log_level, format="%(levelname)s: %(name)s: %(message)s")

    load_from_names(args.names, args.api)


if __name__ == "__main__":
    main()
