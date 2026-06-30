"""One-off probe of yfinance return shapes for NSE tickers. Not part of the package."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import yfinance as yf

TICKERS = ["RELIANCE.NS", "TCS.NS", "INFY.NS"]


def type_name(v: Any) -> str:
    if v is None:
        return "None"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int) and not isinstance(v, bool):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "str"
    if isinstance(v, list):
        inner = type_name(v[0]) if v else "?"
        return f"list[{inner}]"
    if isinstance(v, dict):
        return "dict"
    return type(v).__name__


def summarize_info(info: dict) -> dict:
    return {k: type_name(v) for k, v in sorted(info.items())}


def summarize_df(df: pd.DataFrame | None, name: str) -> dict:
    if df is None:
        return {"status": "None"}
    if df.empty:
        return {"status": "empty", "shape": list(df.shape)}
    out = {
        "status": "ok",
        "shape": list(df.shape),
        "index_dtype": str(df.index.dtype),
        "index_sample": [str(x) for x in df.index[:5]],
        "columns_dtype": str(df.columns.dtype) if hasattr(df.columns, "dtype") else "object",
        "column_sample": [str(c) for c in df.columns[:8]],
        "row_labels": list(df.index.astype(str)),
        "all_row_labels": list(df.index.astype(str)),
        "dtypes": {str(c): str(df[c].dtype) for c in df.columns[:5]},
    }
    # sample values for first column
    if len(df.columns) > 0:
        col0 = df.columns[0]
        sample = {}
        for idx in df.index[:3]:
            val = df.loc[idx, col0]
            sample[str(idx)] = None if pd.isna(val) else float(val) if isinstance(val, (int, float)) else str(val)
        out["value_sample_col0"] = sample
    return out


def main() -> None:
    end = datetime.now()
    start = end - timedelta(days=30)
    report: dict[str, Any] = {"yfinance_version": yf.__version__, "tickers": {}}

    for ticker_sym in TICKERS:
        t = yf.Ticker(ticker_sym)
        entry: dict[str, Any] = {}

        info = t.info or {}
        entry["info"] = {
            "key_count": len(info),
            "fields": summarize_info(info),
            "sample_values": {
                k: info.get(k)
                for k in [
                    "symbol",
                    "shortName",
                    "longName",
                    "exchange",
                    "currency",
                    "financialCurrency",
                    "sector",
                    "industry",
                    "isin",
                    "country",
                    "sharesOutstanding",
                    "impliedSharesOutstanding",
                    "marketCap",
                    "firstTradeDateEpochUtc",
                    "quoteType",
                ]
            },
        }

        for attr in [
            "financials",
            "quarterly_financials",
            "balance_sheet",
            "quarterly_balance_sheet",
            "cashflow",
            "quarterly_cashflow",
        ]:
            df = getattr(t, attr, None)
            entry[attr] = summarize_df(df, attr)
            if df is not None and not df.empty:
                entry[attr]["all_row_labels"] = list(df.index.astype(str))

        hist = t.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))
        entry["history"] = summarize_df(hist, "history")
        if hist is not None and not hist.empty:
            entry["history"]["columns"] = list(hist.columns)
            entry["history"]["dtypes_all"] = {c: str(hist[c].dtype) for c in hist.columns}
            entry["history"]["head"] = {
                str(k): {c: (None if pd.isna(v) else float(v)) for c, v in row.items()}
                for k, row in hist.head(2).iterrows()
            }

        # corporate actions extras
        for attr in ["actions", "dividends", "splits"]:
            obj = getattr(t, attr, None)
            if isinstance(obj, pd.Series):
                entry[attr] = {
                    "type": "Series",
                    "len": len(obj),
                    "dtype": str(obj.dtype),
                    "index_dtype": str(obj.index.dtype),
                    "sample": {str(k): (None if pd.isna(v) else float(v)) for k, v in obj.tail(3).items()},
                }
            elif isinstance(obj, pd.DataFrame):
                entry[attr] = summarize_df(obj, attr)

        report["tickers"][ticker_sym] = entry

    # cross-ticker row label union for financial statements
    unions: dict[str, set[str]] = defaultdict(set)
    for sym, data in report["tickers"].items():
        for attr in [
            "financials",
            "quarterly_financials",
            "balance_sheet",
            "quarterly_balance_sheet",
            "cashflow",
            "quarterly_cashflow",
        ]:
            labels = data.get(attr, {}).get("all_row_labels", [])
            unions[attr].update(labels)

    report["cross_ticker_row_labels"] = {k: sorted(v) for k, v in unions.items()}

    # info key union
    info_keys: set[str] = set()
    for sym, data in report["tickers"].items():
        info_keys.update(data["info"]["fields"].keys())
    report["all_info_keys"] = sorted(info_keys)

    out_path = "/Users/krishvaswani/Documents/Stock Analysis/scripts/yfinance_probe_output.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
