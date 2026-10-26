"""Full comparison with the Excel FINAL file (skipped automatically if the file is not in data/)."""
import os

import numpy as np
import pytest

from conftest import EXCEL_PATH

pytestmark = pytest.mark.skipif(not os.path.exists(EXCEL_PATH), reason="Excel FINAL file not found in data/")


@pytest.fixture(scope="module")
def excel():
    from engine.excel_check import read_excel_cashflow, read_excel_collections, read_excel_curves, read_excel_timeline
    return dict(timeline=read_excel_timeline(EXCEL_PATH), curves=read_excel_curves(EXCEL_PATH),
                collections=read_excel_collections(EXCEL_PATH), cashflow=read_excel_cashflow(EXCEL_PATH))


def test_excel_product_quarters(base, excel):
    got = {n: (t.launch, t.sales_end, t.cons_start, t.cons_end) for n, t in base["timeline"].products.items()}
    assert got == excel["timeline"]


def test_excel_curves(base, excel):
    cv, x = base["curves"], excel["curves"]
    for n in cv.sales_pct:
        assert np.abs(cv.sales_pct[n] - x["sales"][n]).max() < 1e-9
        assert np.abs(cv.cons_pct[n] - x["cons"][n]).max() < 1e-9


def test_excel_cost_phasing(base, excel):
    x = excel["curves"]
    for i, c in enumerate(_project_costs()):
        assert np.abs(base["curves"].cost_pct[c.key] - x["cost"][x["cost_order"][i]]).max() < 1e-9, c.name


def test_excel_collections(base, excel):
    co, x = base["collections"], excel["collections"]
    for n in co.collections:
        assert np.abs(co.collections[n] - x["collections"][n]).max() < 1e-9
    assert np.abs(co.total - x["total"]).max() < 1e-9 and np.abs(co.landowner - x["landowner"]).max() < 1e-9


def test_excel_cash_rows_costs_and_pnl(base, excel):
    cf, cr, x = base["cashflow"], base["costs"], excel["cashflow"]
    assert max(abs(a - b) for a, b in zip(cr.amounts.values(), x["costs"])) < 1e-9
    for o, xo in zip(cf.outflows.values(), x["outflows"]):
        assert np.abs(o - xo).max() < 1e-9
    for k, v in x["rows"].items():
        assert np.abs(getattr(cf, k) - v).max() < 1e-9, k
    for k, v in x["pnl"].items():
        assert abs(cf.pnl[k] - v) < 1e-9, k


def test_excel_all_18_key_metrics(base, excel):
    keys = ["project_irr", "developer_irr", "equity_multiple", "roce", "cagr", "pat_margin", "ebitda_margin", "peak_investment",
            "land_cost_to_gdv", "initial_investment_to_gdv", "breakeven_project_q", "breakeven_developer_q", "payback_q",
            "project_npv", "developer_npv", "developer_irr_post_tax", "largest_quarter_deficit", "cash_multiple"]
    for (label, xv), k in zip(excel["cashflow"]["metrics"].items(), keys):
        pv = base["cashflow"].metrics[k]
        if isinstance(xv, str):
            assert xv == f"Q{pv}", label
        else:
            assert abs(pv - xv) < 1e-6, label


def _project_costs():
    from engine.inputs import sample_project
    return sample_project().costs
