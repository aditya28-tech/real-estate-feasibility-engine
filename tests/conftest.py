"""Shared set-up for all tests: makes the 'engine' package importable and provides ready-made results."""
import copy, os, sys

import pytest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the feasibility_app folder
sys.path.insert(0, BASE)

from engine.inputs import sample_project          # noqa: E402
from engine.cashflow import run_model             # noqa: E402

EXCEL_PATH = os.path.join(BASE, "data", "Feasibility_Engine_FINAL.xlsx")


@pytest.fixture
def project():
    """A fresh copy of the sample project for every test (tests can change it freely)."""
    return sample_project()


@pytest.fixture(scope="session")
def base():
    """The full model results for the sample project (calculated once)."""
    return run_model(sample_project())


def variant(change):
    """Sample project with one change applied, e.g. variant(lambda p: setattr(p.info, 'scenario', 'Worst Case'))."""
    p = sample_project()
    change(p)
    return p
