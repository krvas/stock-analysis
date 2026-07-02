

import json
import os
from typing import Final

REPO_DIR: Final[str] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class URLCache:
    def __init__(self, directory: str, format:str = "json"):
        self.directory = os.path.join(REPO_DIR, directory)
        self.format = format

    def _get_file_path(self, key):
        return os.path.join(self.directory, f"{key}.{self.format}")

    def get(self, key):
        if os.path.exists(self._get_file_path(key)):
            with open(self._get_file_path(key), "r") as f:
                if self.format == "json":
                    return json.load(f)
        return None

    def set(self, key, value):
        with open(self._get_file_path(key), "w") as f:
            if self.format == "json":
                json.dump(value, f)