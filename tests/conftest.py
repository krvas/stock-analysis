"""Pytest fixtures shared across tests."""

import os

import pytest

import src.api.edgartools.cache as cache_mod


def pytest_configure(config: pytest.Config) -> None:
    """Drop every GIT_* variable before any test module is imported.

    The agent shell exports GIT_EDITOR and git rebase -x sets GIT_DIR; a test
    that runs git in a temp repo inherits them, and one once corrupted this
    repo's .git that way.
    """
    for key in [k for k in os.environ if k.startswith("GIT_")]:
        del os.environ[key]


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
