# test_all.py
"""
Master test file. Run this to verify everything works.

Usage:
    python -m pytest tests/test_all.py -v
    python main.py --test
"""

import pytest


# This file just imports all test modules so pytest collects them
from tests.test_db import *
from tests.test_platforms import *
from tests.test_telegram import *
from tests.test_media import *
from tests.test_poster import *


def test_smoke():
    """Basic smoke test - if this fails, something is very wrong."""
    assert True, "Smoke test should always pass"
