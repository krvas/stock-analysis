"""Pytest fixtures shared across tests."""

import pytest

import src.api.edgartools.cache as cache_mod


@pytest.fixture
def use_cache_dir(monkeypatch: pytest.MonkeyPatch):
    """Point ``touch_company_cache`` (which takes no cache_dir) at a directory.

    Returns ``use(cache_dir, size=10)``; patches the cache module's
    ``EDGARTOOLS_CACHE_DIR`` / ``EDGARTOOLS_COMPANY_CACHE_SIZE`` globals.
    """

    def use(cache_dir, size: int = 10):
        monkeypatch.setattr(cache_mod, "EDGARTOOLS_CACHE_DIR", cache_dir)
        monkeypatch.setattr(cache_mod, "EDGARTOOLS_COMPANY_CACHE_SIZE", size)
        return cache_dir

    return use
