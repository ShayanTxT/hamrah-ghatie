"""فیکسچرهای مشترک تستها."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hamrah.core.config import Config  # noqa: E402
from hamrah.core.db import Database  # noqa: E402
from hamrah.core.paths import Paths  # noqa: E402


@pytest.fixture()
def paths(tmp_path):
    return Paths(tmp_path / "data")


@pytest.fixture()
def cfg(paths):
    return Config(paths.config_path)


@pytest.fixture()
def db(paths):
    return Database(paths.db_path)


@pytest.fixture()
def settings(cfg):
    return cfg.as_dict()


@pytest.fixture()
def sample_zim():
    p = ROOT / "samples" / "wikipedia_climate_change_mini.zim"
    return p if p.is_file() else None
