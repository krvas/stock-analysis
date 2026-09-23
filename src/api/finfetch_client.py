import finfetch as ff
import pandas as pd
from base_client import BaseAPIClient

from database import DatabaseManager


class FinfetchClient(BaseAPIClient):

    def fetch(self, ticker: str) -> pd.DataFrame:
        """Fetch financial data for a given ticker using finfetch.

        Args:
            ticker: Stock ticker symbol."""
        with DatabaseManager() as db:
            db.initialize_schema()
            stock = ff.Ticker(ticker)
            db.upsert_dataframe("balance_sheets", stock.balance_sheet)
