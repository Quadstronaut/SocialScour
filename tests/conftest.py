"""Shared pytest fixtures and configuration."""
from __future__ import annotations

from pathlib import Path

import pytest


def pytest_addoption(parser):
    parser.addoption("--e2e", action="store_true", help="run e2e tests")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--e2e"):
        return
    skip_e2e = pytest.mark.skip(reason="needs --e2e")
    for item in items:
        if "e2e" in item.keywords:
            item.add_marker(skip_e2e)


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "component" / "fixtures"
