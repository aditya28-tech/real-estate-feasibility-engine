"""STEP 7 – dashboard content: KPI cards, auto-written takeaways and charts."""
import pytest

from engine.cashflow import run_model
from engine.report import key_metrics_table, kpi_cards, takeaways
from conftest import variant


def test_twelve_kpi_cards_with_correct_values_and_colours(project, base):
    cards = {c["label"]: c for c in kpi_cards(project, base)}
    assert len(cards) == 12
    assert cards["GDV (total revenue)"]["value"] == "₹803.0 Cr"
    assert cards["Developer IRR (pre-tax)"]["value"] == "110.2%" and cards["Developer IRR (pre-tax)"]["status"] == "good"
    assert cards["Equity multiple"]["value"] == "1.47x" and cards["Equity multiple"]["status"] == "review"   # below 2.0x target
    assert cards["Peak investment"]["value"] == "₹34.3 Cr" and "Q2" in cards["Peak investment"]["sub"]
    assert cards["Payback (developer)"]["value"] == "Q8"


def test_takeaways_are_written_from_the_numbers(project, base):
    t = " ".join(takeaways(project, base))
    for piece in ["₹803 Cr", "₹631 Cr", "21.5%", "110%", "₹34.3 Cr", "Q8", "Mar 2029", "₹257.0 Cr", "32% revenue share",
                  "6 of 7 benchmarks", "equity multiple"]:
        assert piece in t, piece


def test_takeaways_change_with_the_deal():
    p = variant(lambda p: setattr(p.info, "deal_type", "Outright"))
    t = " ".join(takeaways(p, run_model(p)))
    assert "Outright deal" in t and "land payment" in t and "landowner receives" not in t


def test_key_metrics_table_has_18_rows(project, base):
    rows = key_metrics_table(project, base)
    assert len(rows) == 18 and rows[1]["value"] == "110.2%" and rows[1]["status"] == "Strong"


@pytest.mark.parametrize("change", [lambda p: None, lambda p: setattr(p.info, "scenario", "Worst Case"),
                                    lambda p: setattr(p.info, "deal_type", "Outright"),
                                    lambda p: setattr(p.info, "project_type", "Villa")])
def test_all_charts_build(change):
    pytest.importorskip("plotly")
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from dashboard import charts
    p = variant(change)
    figs = charts(p, run_model(p))
    assert set(figs) == {"cashflow", "costs", "revenue", "fy", "collections", "cumulative", "gantt"}
    assert all(len(f.data) > 0 for f in figs.values())
