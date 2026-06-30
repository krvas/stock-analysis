#!/usr/bin/env python
"""Quick test of API client imports and instantiation."""

import sys

def test_imports():
    """Test that all API clients can be imported."""
    from src.api import (
        CompaniesClient,
        PricesClient,
        FinancialsClient,
        BalanceSheetsClient,
        CashFlowsClient,
        BaseAPIClient,
    )
    print("✓ All API clients imported successfully")
    return (
        CompaniesClient,
        PricesClient,
        FinancialsClient,
        BalanceSheetsClient,
        CashFlowsClient,
        BaseAPIClient,
    )


def test_converters():
    """Test that all converters can be imported."""
    from src.api.converters import (
        CompanyResponseConverter,
        PricesResponseConverter,
        FinancialsResponseConverter,
        BalanceSheetResponseConverter,
        CashFlowResponseConverter,
    )
    print("✓ All converters imported successfully")
    return (
        CompanyResponseConverter,
        PricesResponseConverter,
        FinancialsResponseConverter,
        BalanceSheetResponseConverter,
        CashFlowResponseConverter,
    )


def test_client_instantiation():
    """Test client instantiation without database."""
    from src.api import (
        CompaniesClient,
        PricesClient,
        FinancialsClient,
        BalanceSheetsClient,
        CashFlowsClient,
    )

    companies_client = CompaniesClient(db=None)
    assert companies_client.client_name == "CompaniesClient"
    print(f"✓ CompaniesClient created: {companies_client.client_name}")

    prices_client = PricesClient(db=None)
    assert prices_client.client_name == "PricesClient"
    print(f"✓ PricesClient created: {prices_client.client_name}")

    financials_client = FinancialsClient(db=None)
    assert financials_client.client_name == "FinancialsClient"
    print(f"✓ FinancialsClient created: {financials_client.client_name}")

    balance_sheets_client = BalanceSheetsClient(db=None)
    assert balance_sheets_client.client_name == "BalanceSheetsClient"
    print(f"✓ BalanceSheetsClient created: {balance_sheets_client.client_name}")

    cash_flows_client = CashFlowsClient(db=None)
    assert cash_flows_client.client_name == "CashFlowsClient"
    print(f"✓ CashFlowsClient created: {cash_flows_client.client_name}")


def test_converters_with_sample_data():
    """Test converters with sample API responses."""
    from src.api.converters import (
        CompanyResponseConverter,
        PricesResponseConverter,
        FinancialsResponseConverter,
        BalanceSheetResponseConverter,
        CashFlowResponseConverter,
    )
    import pandas as pd

    # Test CompanyResponseConverter
    company_data = [
        {
            "symbol": "TCS",
            "exchange": "NSE",
            "company_name": "Tata Consultancy Services",
            "sector": "IT",
            "market_cap": 1500000.0,
        }
    ]
    companies_df = CompanyResponseConverter.convert(company_data)
    assert len(companies_df) == 1
    assert companies_df.iloc[0]["symbol"] == "TCS"
    print("✓ CompanyResponseConverter converted sample data")

    # Test PricesResponseConverter
    prices_data = [
        {
            "date": "2024-05-20",
            "open": 3500.0,
            "high": 3600.0,
            "low": 3480.0,
            "close": 3550.0,
            "volume": 1000000,
        }
    ]
    prices_df = PricesResponseConverter.convert(prices_data, "TCS", "NSE")
    assert len(prices_df) == 1
    assert prices_df.iloc[0]["symbol"] == "TCS"
    assert prices_df.iloc[0]["exchange"] == "NSE"
    print("✓ PricesResponseConverter converted sample data")

    # Test FinancialsResponseConverter
    financials_data = [
        {
            "fiscal_year": 2024,
            "revenue": 250000.0,
            "net_profit": 50000.0,
            "eps_basic": 25.5,
        }
    ]
    financials_df = FinancialsResponseConverter.convert(financials_data, "TCS", "NSE")
    assert len(financials_df) == 1
    assert financials_df.iloc[0]["symbol"] == "TCS"
    print("✓ FinancialsResponseConverter converted sample data")

    # Test BalanceSheetResponseConverter
    balance_sheet_data = [
        {
            "period_end_date": "2024-03-31",
            "period_type": "annual",
            "total_assets": 500000.0,
            "total_liabilities": 200000.0,
        }
    ]
    balance_sheet_df = BalanceSheetResponseConverter.convert(
        balance_sheet_data, "TCS", "NSE"
    )
    assert len(balance_sheet_df) == 1
    assert balance_sheet_df.iloc[0]["symbol"] == "TCS"
    print("✓ BalanceSheetResponseConverter converted sample data")

    # Test CashFlowResponseConverter
    cash_flow_data = [
        {
            "period_end_date": "2024-03-31",
            "period_type": "annual",
            "operating_cash_flow": 100000.0,
            "free_cash_flow": 80000.0,
        }
    ]
    cash_flow_df = CashFlowResponseConverter.convert(cash_flow_data, "TCS", "NSE")
    assert len(cash_flow_df) == 1
    assert cash_flow_df.iloc[0]["symbol"] == "TCS"
    print("✓ CashFlowResponseConverter converted sample data")


if __name__ == "__main__":
    print("Testing API wrapper classes...\n")

    try:
        test_imports()
        test_converters()
        test_client_instantiation()
        test_converters_with_sample_data()
        print("\n✅ All tests passed!")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
