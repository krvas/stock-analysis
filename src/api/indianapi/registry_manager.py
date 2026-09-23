
import json
import os
from typing import Any, Final

API_NAME_BY_SYMBOL_PATH: Final[str] = os.path.join(os.path.dirname(__file__), "registry_names.json")
FIELD_KEYS_PATH: Final[str] = os.path.join(os.path.dirname(__file__), "registry_field_keys.json")

# TODO: This seems redundant with url_cache.py. We should consolidate them.
# TODO: We should add functionality to automatically update the registry files
# for stocks that are pulled

class RegistryManager:
    def __init__(self):
        self.api_name_by_symbol = None
        self.field_keys = None
        self.dirty = { "api_name_by_symbol": False, "field_keys": False }
    
    def _read_json(self, filename: str) -> dict[str, Any]:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def _write_json(self, filename: str, data: dict[str, Any]) -> None:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    
    def get_api_name_by_symbol(self) -> dict[str, str]:
        if self.api_name_by_symbol is None:
            self.api_name_by_symbol = self._read_json(API_NAME_BY_SYMBOL_PATH)
        return self.api_name_by_symbol

    def get_field_keys(self) -> dict[str, tuple[str, ...]]:
        if self.field_keys is None:
            self.field_keys = self._read_json(FIELD_KEYS_PATH)
        return self.field_keys

    def get_income_statement_keys(self) -> dict[str, tuple[str, ...]]:
        field_keys = self.get_field_keys()
        return field_keys.get("income_statement", {})
    
    def get_cash_flow_keys(self) -> dict[str, tuple[str, ...]]:
        field_keys = self.get_field_keys()
        return field_keys.get("cash_flow", {})
    
    def get_balance_sheet_keys(self) -> dict[str, tuple[str, ...]]:
        field_keys = self.get_field_keys()
        return field_keys.get("balance_sheet", {})

    def close(self) -> None:
        if self.dirty["api_name_by_symbol"]:
            self._write_json(API_NAME_BY_SYMBOL_PATH, self.api_name_by_symbol)
        if self.dirty["field_keys"]:
            self._write_json(FIELD_KEYS_PATH, self.field_keys)