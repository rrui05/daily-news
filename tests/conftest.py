from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture
def fixed_now() -> datetime:
    """A timezone-aware clock used by every freshness-boundary test."""

    return datetime(2026, 8, 17, 12, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

