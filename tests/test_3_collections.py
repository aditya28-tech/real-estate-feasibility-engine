"""STEP 3 – collections: every rupee booked is collected, two methods agree, worked example holds."""
import numpy as np
import pytest

from engine.cashflow import run_model
from engine.collections import verify_by_cohorts
from conftest import variant


def test_collections_equal_revenue_for_every_product(base):
    co, cv = base["collections"], base["curves"]
    for name, cash in co.collections.items():
        assert abs(cash.sum() - cv.revenue[name]) < 1e-6
        assert co.receivables[name].min() > -1e-6                # never paid before booked
        assert abs(co.receivables[name][-1]) < 1e-6              # fully cleared


def test_worked_example_villa_q5_is_21_39_crore(base):
    assert abs(base["collections"].collections["Villas"][4] - 21.388888888888889) < 1e-9


def test_jv_split_32_68(base):
    co = base["collections"]
    assert abs(co.landowner.sum() - 256.96) < 1e-6 and abs(co.developer.sum() - 546.04) < 1e-6


def test_villa_milestones_fall_due_in_excel_quarters(base):
    due = {s.name: s.due_q for s in base["collections"].schedule if s.product == "Villas" and s.due_q}
    assert due == {"Commencement of construction": 5, "Ground plinth": 7, "First floor roof casting": 8,
                   "Second floor roof casting": 10, "Third floor roof casting": 11,
                   "Completion certificate (CC)": 14, "Possession": 15}


SCENARIOS = {
    "base": lambda p: None,
    "worst": lambda p: setattr(p.info, "scenario", "Worst Case"),
    "best": lambda p: setattr(p.info, "scenario", "Best Case"),
    "lag0": lambda p: setattr(p, "catch_up_lag", 0),
    "lag2": lambda p: setattr(p, "catch_up_lag", 2),
    "tower17": lambda p: setattr(p.products[1], "clp_plan", "CLP – 17-Floor Tower"),
    "apartments": lambda p: setattr(p.info, "project_type", "Apartments"),
    "longer_build": lambda p: setattr(p.products[1], "construction_duration_q", 24),
}


@pytest.mark.parametrize("name", SCENARIOS)
def test_two_independent_methods_agree(name):
    r = run_model(variant(SCENARIOS[name]))
    assert r["problems"] == []
    assert verify_by_cohorts(variant(SCENARIOS[name]), r["timeline"], r["curves"], r["collections"]) < 1e-9
    assert abs(r["collections"].total.sum() - sum(r["curves"].revenue.values())) < 1e-6
