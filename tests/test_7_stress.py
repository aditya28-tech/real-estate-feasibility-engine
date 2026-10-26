"""STEP 8 – stress testing & Monte Carlo: levers = Excel STRESS sheet, inputs never changed, Monte Carlo reproducible."""
import copy, os

import numpy as np
import pytest

from engine.inputs import to_dict
from engine.stress import McRanges, headroom, monte_carlo, one_way, outcome, scenario_table, stressed, two_way
from conftest import EXCEL_PATH


def test_stressing_never_changes_the_original(project):
    before = to_dict(project)
    stressed(project, price=-0.2, cost=0.3, speed=2, delay=3)
    outcome(project, price=-0.1)
    assert to_dict(project) == before


def test_neutral_levers_give_the_base_case(project, base):
    o = outcome(project)
    assert abs(o["developer_irr"] - base["cashflow"].metrics["developer_irr"]) < 1e-12 and abs(o["pat"] - base["cashflow"].pnl["pat"]) < 1e-9


# golden values from the Excel STRESS sheet
@pytest.mark.parametrize("lever, value, irr, peak, payback", [
    ("price", -0.15, 0.7309871, 33.8055449, 10), ("price", -0.10, 0.8615225333012542, 33.9661, 8), ("price", 0.15, 1.4224, 34.7691, 8),
    ("cost", 0.20, 0.7795, 34.2873, 10), ("speed", 2.0, 0.5062, 35.3701, 16), ("delay", 6, 0.5175, 40.9584, 14)])
def test_one_way_matches_excel(project, lever, value, irr, peak, payback):
    o = outcome(project, **{lever: value})
    assert abs(o["developer_irr"] - irr) < 1e-4 and abs(o["peak"] - peak) < 1e-4 and o["payback_q"] == payback


def test_scenarios_match_excel(project):
    rows = {r["scenario"]: r for r in scenario_table(project)}
    assert abs(rows["Best Case"]["developer_irr"] - 1.5076) < 1e-4 and abs(rows["Best Case"]["gdv"] - 843.15) < 1e-9
    assert abs(rows["Worst Case"]["developer_irr"] - 0.40241041469118866) < 1e-9 and rows["Worst Case"]["payback_q"] == 18


def test_heat_map_corner_matches_excel(project):
    g = two_way(project, "cost", [0.0, 0.20], "price", [-0.10, 0.10], "developer_irr")
    assert abs(g[1, 0] - 0.5085) < 1e-4 and abs(g[0, 1] - 1.3208) < 1e-4


def test_headroom_matches_excel_and_is_consistent(project):
    h = headroom(project)
    assert abs(h["price_to_zero_ebitda"] - (-0.37664608391863835)) < 1e-9
    assert abs(h["cost_to_zero_ebitda"] - 0.6375542865029586) < 1e-9
    assert abs(outcome(project, price=h["price_to_zero_ebitda"])["ebitda"]) < 1e-6          # EBITDA really is zero there
    assert abs(outcome(project, price=h["price_to_hurdle"])["developer_irr"] - 0.18) < 1e-6   # IRR really is the hurdle there


def test_monte_carlo_is_reproducible_and_sensible(project):
    a = monte_carlo(project, n=60, seed=7)
    b = monte_carlo(project, n=60, seed=7)
    assert np.allclose(a["irr"], b["irr"]) and a["p_irr_above_hurdle"] == b["p_irr_above_hurdle"]
    assert 0 <= a["p_irr_above_hurdle"] <= 1 and a["irr_p10"] <= a["irr_p50"] <= a["irr_p90"]
    assert a["failed_runs"] == 0


def test_monte_carlo_with_no_uncertainty_equals_base(project, base):
    r = McRanges((0, 0, 0), (0, 0, 0), (1, 1, 1), {0: 1.0})
    mc = monte_carlo(project, r, n=10)
    assert np.allclose(mc["irr"], base["cashflow"].metrics["developer_irr"])


def test_harsher_ranges_lower_the_probability(project):
    soft = monte_carlo(project, n=80, seed=1)
    harsh = monte_carlo(project, McRanges((-0.45, -0.30, -0.15), (0.20, 0.35, 0.50), (1.5, 2.0, 2.5), {2: 0.5, 3: 0.5}), n=80, seed=1)
    assert harsh["irr_p50"] < soft["irr_p50"] and harsh["p_irr_above_hurdle"] <= soft["p_irr_above_hurdle"]


@pytest.mark.skipif(not os.path.exists(EXCEL_PATH), reason="Excel FINAL file not found in data/")
def test_full_stress_sheet_matches_excel(project):
    from engine.excel_check import read_excel_stress
    x = read_excel_stress(EXCEL_PATH)
    for sec, lever in [("C1", "price"), ("C2", "cost"), ("C3", "speed"), ("C4", "delay")]:
        for py, ex in zip(one_way(project, lever, [r["value"] for r in x[sec]]), x[sec]):
            assert abs(py["developer_irr"] - ex["Developer IRR"]) < 1e-9 and abs(py["peak"] - ex["Peak investment (₹ Cr)"]) < 1e-9
            assert f"Q{py['payback_q']}" == ex["Payback"]
    for sec, (rl, cl, met) in {"D1": ("cost", "price", "developer_irr"), "D2": ("cost", "price", "pat"), "D3": ("speed", "delay", "peak")}.items():
        d = x[sec]
        assert np.abs(two_way(project, rl, d["row_values"], cl, d["col_values"], met) - d["grid"]).max() < 1e-9


def test_stress_charts_build(project):
    pytest.importorskip("plotly")
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import stress_view as sv
    T = sv.compute_tables(project)
    mc = monte_carlo(project, n=30)
    figs = [sv.fig_one_way(T["one_way"]["price"], "price", 0.18), sv.fig_tornado(T["tornado"]),
            sv.fig_heat(T["irr_grid"], [0, .05, .1, .15, .2], [-.1, -.05, 0, .05, .1], "{:+.0%}", "{:+.0%}", "t", "{:.0%}"),
            sv.fig_mc_hist(mc, 0.18), sv.fig_mc_exceedance(mc, 0.18), sv.fig_mc_scatter(mc)]
    assert all(len(f.data) > 0 for f in figs)
