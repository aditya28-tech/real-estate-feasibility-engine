"""STEP 2 – timeline and curves: shapes always total 100%, quarters match Excel, links and scenarios work."""
import math

import numpy as np
import pytest

from engine.curves import build_curves, curve_weights, spread
from engine.timeline import build_timeline, quarter_end, fy_label
from datetime import date
from conftest import variant

CURVES = ["Upfront", "Even", "Front-loaded", "Back-loaded", "S-curve"]


@pytest.mark.parametrize("name", CURVES)
@pytest.mark.parametrize("n", [1, 2, 3, 7, 12, 16, 24, 40])
def test_every_curve_totals_exactly_100_percent(name, n):
    w = curve_weights(name, n)
    assert len(w) == n and abs(w.sum() - 1) < 1e-12 and (w >= 0).all()


def test_s_curve_is_symmetric_and_peaks_in_middle():
    w = curve_weights("S-curve", 12)
    assert np.allclose(w, w[::-1]) and w.argmax() in (5, 6)


def test_front_and_back_loaded_mirror_each_other():
    assert np.allclose(curve_weights("Front-loaded", 9), curve_weights("Back-loaded", 9)[::-1])


def test_spread_places_curve_in_window():
    s = spread("Even", 5, 8)
    assert s[:4].sum() == 0 and abs(s[4:8].sum() - 1) < 1e-12 and s[8:].sum() == 0


def test_calendar_and_financial_year():
    assert quarter_end(date(2027, 6, 30), 1) == date(2027, 6, 30)
    assert quarter_end(date(2027, 6, 30), 3) == date(2027, 12, 31)
    assert quarter_end(date(2027, 6, 30), 4) == date(2028, 3, 31)
    assert fy_label(date(2027, 6, 30)) == "FY 2027-28" and fy_label(date(2028, 3, 31)) == "FY 2027-28"


EXCEL_QUARTERS = {"Villas": (3, 10, 4, 15), "Apartments – Towers A & B": (4, 15, 5, 20),
                  "Studios": (6, 13, 6, 17), "High-street retail": (8, 15, 6, 17)}


def test_product_quarters_match_excel(base):
    tl = base["timeline"]
    got = {n: (t.launch, t.sales_end, t.cons_start, t.cons_end) for n, t in tl.products.items()}
    assert got == EXCEL_QUARTERS and tl.last_q == 20


def test_linked_products_follow_the_lead_product():
    tl = build_timeline(variant(lambda p: setattr(p.products[0], "launch_q", 5)))
    assert tl.products["Villas"].launch == 5
    assert tl.products["Apartments – Towers A & B"].launch == 6        # 1 quarter after villas
    assert tl.products["High-street retail"].launch == 10              # 4 quarters after apartments


def test_fallback_to_fixed_quarter_when_linked_product_inactive():
    tl = build_timeline(variant(lambda p: setattr(p.info, "project_type", "Apartments")))
    t = tl.products["Apartments – Towers A & B"]
    assert t.launch == 4 and "fallback" in t.note


def test_worst_case_delays_and_slows_sales():
    tl = build_timeline(variant(lambda p: setattr(p.info, "scenario", "Worst Case")))
    v = tl.products["Villas"]
    assert (v.launch, v.sales_end, v.cons_start) == (5, 16, 6)          # +2 delay, 8 x 1.5 = 12 quarters


def test_longer_construction_extends_project():
    def change(p): p.products[1].construction_duration_q = 24
    assert build_timeline(variant(change)).last_q == 28


def test_all_curve_rows_total_100_percent(base):
    cv = base["curves"]
    for arr in list(cv.sales_pct.values()) + list(cv.cons_pct.values()):
        assert abs(arr.sum() - 1) < 1e-9
    for k, arr in cv.cost_pct.items():
        assert arr is not None and (abs(arr.sum() - 1) < 1e-9 or arr.sum() == 0)
    assert abs(cv.cons_cum["Villas"][-1] - 1) < 1e-9
