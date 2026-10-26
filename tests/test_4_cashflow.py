"""STEP 4 – costs, cash flow, P&L and returns: golden values (verified against Excel) and accounting identities."""
import itertools

import numpy as np
import pytest

from engine.cashflow import irr, npv, run_model
from conftest import variant

# golden values = the Excel FINAL model's results for the sample project
GOLDEN = dict(revenue=803.0, total_cost=630.6053209296, ebitda=172.3946790704, pat=127.572062512096,
              developer_irr=1.1017637673975016, project_irr=4.490612021677777, developer_npv=90.62811362965084,
              peak_investment=34.2873209296, equity_multiple=1.4732968016982388, roce=1.2009637125967791,
              cagr=0.4033845607907973, initial_investment=28.7093901776)


def test_pnl_matches_excel(base):
    pnl = base["cashflow"].pnl
    for k in ("revenue", "total_cost", "ebitda", "pat"):
        assert abs(pnl[k] - GOLDEN[k]) < 1e-6, k


def test_key_metrics_match_excel(base):
    m = base["cashflow"].metrics
    for k in ("developer_irr", "project_irr", "developer_npv", "peak_investment", "equity_multiple", "roce", "cagr", "initial_investment"):
        assert abs(m[k] - GOLDEN[k]) < 1e-6, k
    assert (m["peak_quarter"], m["payback_q"], m["breakeven_project_q"], m["breakeven_developer_q"]) == (2, 8, 3, 3)


def test_bar_and_land_amounts(base):
    a = base["costs"].amounts
    assert abs(a["bar"] - 3.154574336) < 1e-6 and abs(a["land"] - 256.96) < 1e-6 and abs(a["brok"] - 2.124) < 1e-9


@pytest.mark.parametrize("name, change, irr_, peak, payback", [
    ("worst", lambda p: setattr(p.info, "scenario", "Worst Case"), 0.40241041469118866, 36.3601955115398, 18),
    ("outright_llp", lambda p: (setattr(p.info, "deal_type", "Outright"), setattr(p.land, "payment_curve", "Even"),
                                setattr(p.land, "payment_end_q", 4), setattr(p.info, "entity", "LLP")),
     0.3561027999778046, 203.09589048611082, 12),
])
def test_other_scenarios_match_excel(name, change, irr_, peak, payback):
    m = run_model(variant(change))["cashflow"].metrics
    assert abs(m["developer_irr"] - irr_) < 1e-6 and abs(m["peak_investment"] - peak) < 1e-6 and m["payback_q"] == payback


def test_irr_and_npv_helpers_on_known_numbers():
    assert abs(irr(np.array([-100.0, 110.0])) - 0.10) < 1e-9
    assert abs(irr(np.array([-100.0, 0.0, 121.0])) - 0.10) < 1e-9
    assert irr(np.array([100.0, 50.0])) is None                        # no investment -> no IRR
    assert abs(npv(0.10, np.array([110.0])) - 100.0) < 1e-9


# accounting identities that must hold in EVERY situation
SITUATIONS = list(itertools.product(["Base Case", "Best Case", "Worst Case"], ["JV", "Outright"],
                                    ["Mixed Development", "Villa", "Apartments"], [0, 1, 2]))


@pytest.mark.parametrize("scenario, deal, ptype, lag", SITUATIONS)
def test_accounting_identities_hold(scenario, deal, ptype, lag):
    def change(p):
        p.info.scenario, p.info.deal_type, p.info.project_type, p.catch_up_lag = scenario, deal, ptype, lag
    p = variant(change)
    r = run_model(p)
    cf, cr, co = r["cashflow"], r["costs"], r["collections"]
    assert r["problems"] == []
    assert abs(cf.developer_cf.sum() - cf.pnl["ebitda"]) < 1e-6                     # cash = profit
    for c in p.costs:                                                                # each cost paid exactly once
        expected = 0.0 if (deal == "JV" and c.key == "land") else cr.amounts[c.key]
        assert abs(cf.outflows[c.key].sum() - expected) < 1e-6, c.name
    assert abs(cf.lo_paid.sum() - co.landowner.sum()) < 1e-6                         # landowner paid his share
    assert abs(cf.pnl["revenue"] - cf.pnl["total_cost"] - cf.pnl["ebitda"]) < 1e-9
    assert cf.metrics["peak_investment"] >= 0
