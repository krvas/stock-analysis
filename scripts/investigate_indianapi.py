"""One-off probe of Indian API return shapes. Not part of the package."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_URL = "https://stock.indianapi.in"
OUT_PATH = Path(__file__).resolve().parent / "indianapi_probe_output.json"
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"

TICKERS_EXACT = [
    "HDFC Bank",
    "ICICI Bank",
    "State Bank of India",
    "Bajaj Finance",
    "SBI Life",
    "Tata Consultancy Services",
    "Infosys",
    "Hindustan Unilever",
    "Sun Pharma",
    "Tata Motors",
    "Tata Steel",
    "Reliance Industries",
    "DLF",
    "Bharti Airtel",
    "NTPC",
]

NAME_VARIANTS = {
    "Tata Consultancy Services": ["TCS", "Tata Consultancy", "tcs"],
}

HISTORICAL_TICKERS = ["Reliance Industries", "HDFC Bank", "Tata Steel"]
CORPORATE_ACTION_TICKERS = ["Reliance Industries", "HDFC Bank"]

request_log: list[dict[str, Any]] = []
request_count = 0


def load_api_key() -> str:
    for line in ENV_PATH.read_text().splitlines():
        if line.startswith("INDIAN_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("INDIAN_API_KEY not found in .env")


def api_get(path: str, params: dict[str, str]) -> tuple[int, Any]:
    global request_count
    request_count += 1
    qs = urllib.parse.urlencode(params)
    url = f"{BASE_URL}{path}?{qs}"
    req = urllib.request.Request(
        url,
        headers={"x-api-key": load_api_key(), "Accept": "application/json"},
    )
    entry = {
        "n": request_count,
        "ts": datetime.now(timezone.utc).isoformat(),
        "method": "GET",
        "path": path,
        "params": params,
        "url": url,
    }
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read()
            entry["status"] = resp.status
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                data = {"_raw": body.decode("utf-8", errors="replace")[:500]}
            entry["ok"] = True
            request_log.append(entry)
            return resp.status, data
    except urllib.error.HTTPError as e:
        entry["status"] = e.code
        entry["ok"] = False
        try:
            entry["error_body"] = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            entry["error_body"] = str(e)
        request_log.append(entry)
        return e.code, {"error": entry.get("error_body", str(e))}
    except Exception as e:
        entry["ok"] = False
        entry["error"] = str(e)
        request_log.append(entry)
        return 0, {"error": str(e)}


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


def sample_value_types(values: list[Any], limit: int = 200) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for item in values[:limit]:
        counts[type_name(item)] += 1
    return dict(counts)


def analyze_financials(financials: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"raw_type": type_name(financials)}
    if not isinstance(financials, list):
        return out

    out["period_count"] = len(financials)
    if not financials:
        return out

    period_samples = []
    statement_type_keys: set[str] = set()
    all_line_keys: dict[str, set[str]] = defaultdict(set)
    value_type_counts: dict[str, int] = defaultdict(int)
    missing_value_patterns: dict[str, int] = defaultdict(int)
    period_meta_samples: list[dict[str, Any]] = []

    for period in financials[:5]:
        if not isinstance(period, dict):
            continue
        meta = {k: v for k, v in period.items() if k not in ("INC", "BAL", "CAS", "financials")}
        period_meta_samples.append({k: (type_name(v), v) for k, v in meta.items()})

        for stmt_key in ("INC", "BAL", "CAS"):
            if stmt_key in period:
                statement_type_keys.add(stmt_key)
                stmt = period[stmt_key]
                if isinstance(stmt, list):
                    for row in stmt:
                        if isinstance(row, dict):
                            k = row.get("key")
                            if k:
                                all_line_keys[stmt_key].add(str(k))
                            val = row.get("value")
                            value_type_counts[type_name(val)] += 1
                            if val is None:
                                missing_value_patterns["null"] += 1
                            elif val == "":
                                missing_value_patterns["empty_string"] += 1
                            elif val == "-":
                                missing_value_patterns["dash"] += 1
                            elif val == "0" or val == "0.0":
                                missing_value_patterns["zero_string"] += 1
                            elif isinstance(val, str) and val.startswith("-"):
                                missing_value_patterns["negative_string"] += 1

        period_samples.append(
            {
                "top_keys": sorted(period.keys()),
                "stmt_keys_present": [k for k in ("INC", "BAL", "CAS") if k in period],
            }
        )

    out["period_samples"] = period_samples
    out["period_meta_samples"] = period_meta_samples
    out["statement_type_keys"] = sorted(statement_type_keys)
    out["line_item_keys"] = {k: sorted(v) for k, v in all_line_keys.items()}
    out["value_type_counts"] = dict(value_type_counts)
    out["missing_value_patterns"] = dict(missing_value_patterns)

    # First row sample per statement type from latest period
    latest = financials[0] if financials else {}
    row_samples = {}
    if isinstance(latest, dict):
        for stmt_key in ("INC", "BAL", "CAS"):
            stmt = latest.get(stmt_key)
            if isinstance(stmt, list) and stmt:
                row_samples[stmt_key] = stmt[:3]
    out["latest_row_samples"] = row_samples

    # Period derivation fields
    period_fields = defaultdict(set)
    for period in financials:
        if isinstance(period, dict):
            for k, v in period.items():
                if k not in ("INC", "BAL", "CAS"):
                    period_fields[k].add(type_name(v))
    out["period_level_fields"] = {k: sorted(v) for k, v in period_fields.items()}

    return out


def analyze_stock_response(data: dict[str, Any]) -> dict[str, Any]:
    if "error" in data and len(data) <= 2:
        return {"status": "error", "error": data.get("error")}

    profile = data.get("companyProfile") or {}
    reusable = data.get("stockDetailsReusableData") or {}

    return {
        "status": "ok",
        "companyName": data.get("companyName"),
        "industry": data.get("industry"),
        "top_level_keys": sorted(data.keys()),
        "companyProfile_keys": sorted(profile.keys()) if isinstance(profile, dict) else [],
        "companyProfile_sample": {
            k: profile.get(k)
            for k in [
                "tickerId",
                "commonName",
                "mgIndustry",
                "mgSector",
                "exchangeCodeNsi",
                "exchangeCodeBse",
                "isin",
                "stockType",
                "incorporationDate",
                "listingDate",
                "sharesOutstanding",
                "marketCap",
            ]
            if isinstance(profile, dict)
        },
        "reusable_keys": sorted(reusable.keys()) if isinstance(reusable, dict) else [],
        "reusable_sample": {
            k: reusable.get(k)
            for k in [
                "tickerId",
                "nseSymbol",
                "bseSymbol",
                "isin",
                "exchangeCodeNsi",
                "exchangeCodeBse",
            ]
            if isinstance(reusable, dict)
        },
        "currentPrice": data.get("currentPrice"),
        "financials": analyze_financials(data.get("financials")),
        "initialStockFinancialData_keys": (
            sorted(data["initialStockFinancialData"].keys())
            if isinstance(data.get("initialStockFinancialData"), dict)
            else type_name(data.get("initialStockFinancialData"))
        ),
    }


def analyze_historical(data: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"raw_type": type_name(data)}
    if not isinstance(data, dict):
        return out
    datasets = data.get("datasets")
    if not isinstance(datasets, list):
        out["keys"] = sorted(data.keys())
        return out
    out["dataset_count"] = len(datasets)
    out["metrics"] = []
    for ds in datasets:
        if not isinstance(ds, dict):
            continue
        values = ds.get("values") or []
        sample = values[0] if values else None
        out["metrics"].append(
            {
                "metric": ds.get("metric"),
                "label": ds.get("label"),
                "value_count": len(values),
                "first_value": sample,
                "last_value": values[-1] if values else None,
                "first_value_types": [type_name(x) for x in sample] if isinstance(sample, list) else None,
            }
        )
    return out


def analyze_corporate_actions(data: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"raw_type": type_name(data)}
    if isinstance(data, dict):
        out["keys"] = sorted(data.keys())
        for k, v in data.items():
            if isinstance(v, list) and v:
                out[f"{k}_sample"] = v[:3]
                out[f"{k}_count"] = len(v)
    elif isinstance(data, list):
        out["count"] = len(data)
        out["sample"] = data[:5]
        if data:
            out["item_keys"] = sorted(data[0].keys()) if isinstance(data[0], dict) else None
    return out


def main() -> None:
    report: dict[str, Any] = {
        "investigation_date": datetime.now(timezone.utc).isoformat(),
        "base_url": BASE_URL,
        "tickers": {},
        "name_resolution_tests": {},
        "historical": {},
        "corporate_actions": {},
    }

    for name in TICKERS_EXACT:
        status, data = api_get("/stock", {"name": name})
        report["tickers"][name] = {
            "http_status": status,
            "analysis": analyze_stock_response(data if isinstance(data, dict) else {"error": data}),
        }

    for exact, variants in NAME_VARIANTS.items():
        report["name_resolution_tests"][exact] = {}
        for variant in variants:
            status, data = api_get("/stock", {"name": variant})
            resolved = None
            if isinstance(data, dict) and "error" not in data:
                profile = data.get("companyProfile") or {}
                resolved = data.get("companyName") or (
                    profile.get("commonName") if isinstance(profile, dict) else None
                )
            report["name_resolution_tests"][exact][variant] = {
                "http_status": status,
                "resolved_companyName": resolved,
                "error": data.get("error") if isinstance(data, dict) else str(data),
            }

    for name in HISTORICAL_TICKERS:
        # docs show both stock_name and symbol — test stock_name first
        status, data = api_get(
            "/historical_data",
            {"stock_name": name, "period": "1yr", "filter": "price"},
        )
        report["historical"][name] = {
            "http_status": status,
            "params": "stock_name",
            "analysis": analyze_historical(data),
        }

    for name in CORPORATE_ACTION_TICKERS:
        status, data = api_get("/corporate_actions", {"stock_name": name})
        report["corporate_actions"][name] = {
            "http_status": status,
            "analysis": analyze_corporate_actions(data),
        }

    # Cross-ticker line item union
    unions: dict[str, set[str]] = defaultdict(set)
    bank_names = {"HDFC Bank", "ICICI Bank", "State Bank of India", "Bajaj Finance", "SBI Life"}
    industrial_names = {"Tata Steel", "Hindustan Unilever", "Tata Motors", "Sun Pharma"}

    bank_keys: dict[str, set[str]] = defaultdict(set)
    industrial_keys: dict[str, set[str]] = defaultdict(set)

    for name, entry in report["tickers"].items():
        fin = entry.get("analysis", {}).get("financials", {})
        line_keys = fin.get("line_item_keys", {})
        for stmt, keys in line_keys.items():
            unions[stmt].update(keys)
            if name in bank_names:
                bank_keys[stmt].update(keys)
            if name in industrial_names:
                industrial_keys[stmt].update(keys)

    report["cross_ticker_line_keys"] = {k: sorted(v) for k, v in unions.items()}
    report["bank_only_keys"] = {
        stmt: sorted(bank_keys[stmt] - industrial_keys[stmt])
        for stmt in bank_keys
    }
    report["industrial_only_keys"] = {
        stmt: sorted(industrial_keys[stmt] - bank_keys[stmt])
        for stmt in industrial_keys
    }

    report["request_log"] = request_log
    report["request_count_session"] = request_count

    OUT_PATH.write_text(json.dumps(report, indent=2, default=str))
    print(f"Wrote {OUT_PATH}")
    print(f"Session API requests: {request_count}")


if __name__ == "__main__":
    main()
