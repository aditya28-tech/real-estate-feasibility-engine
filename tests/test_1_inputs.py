"""STEP 1 – input structure: the sample is valid, saving works, and the checks catch mistakes."""
import copy
from datetime import date

from engine.inputs import CRORE, load_project, save_project, to_dict, validate


def test_sample_project_has_no_input_errors(project):
    assert validate(project) == []


def test_sample_matches_excel_inputs(project):
    act = project.active_products()
    assert len(act) == 4
    assert sum(p.area_sqft for p in act) == 920_000
    assert sum(p.area_sqft * p.rate for p in act) / CRORE == 803.0
    assert abs(sum(p.area_sqft * p.construction_rate for p in act) / CRORE - 270.4) < 1e-9


def test_save_and_load_gives_identical_project(project, tmp_path):
    path = tmp_path / "p.json"
    save_project(project, str(path))
    assert to_dict(load_project(str(path))) == to_dict(project)


def _errors_after(project, change):
    p = copy.deepcopy(project)
    change(p)
    return " | ".join(validate(p))


def test_catches_non_quarter_end_start_date(project):
    assert "quarter-end" in _errors_after(project, lambda p: setattr(p.info, "start_date", date(2027, 7, 15)))


def test_catches_payment_plan_not_100_percent(project):
    assert "must be exactly 100%" in _errors_after(project, lambda p: setattr(p.plan("CLP – Apartment").milestones[2], "pct", 0.05))


def test_catches_link_to_product_below(project):
    assert "ABOVE" in _errors_after(project, lambda p: setattr(p.products[1].timing, "launch_link_product", "Studios"))


def test_catches_booking_lag_above_12(project):
    assert "booking lag" in _errors_after(project, lambda p: setattr(p.plan("CLP – Apartment").milestones[1], "value", 13))


def test_catches_zone_shares_above_100(project):
    assert "Zone shares" in _errors_after(project, lambda p: setattr(p.zones[0], "share", 0.9))


def test_catches_advance_instalments_too_big(project):
    assert "exceed the total advance" in _errors_after(project, lambda p: setattr(p.initial, "dd_amount", 50))


def test_catches_invalid_bar_combination(project):
    assert "No BAR %" in _errors_after(project, lambda p: setattr(p.bar, "land_use", "Industrial"))


def test_catches_no_active_product(project):
    def change(p):
        p.info.project_type = "Plotted"
    assert "No product is active" in _errors_after(project, change)


def test_catches_duplicate_product_names(project):
    assert "different name" in _errors_after(project, lambda p: setattr(p.products[2], "name", "Villas"))


def test_project_type_filters_products(project):
    expected = {"Villa": ["Villas"],
                "Apartments": ["Apartments – Towers A & B", "Studios", "High-street retail"],
                "Mixed Development": ["Villas", "Apartments – Towers A & B", "Studios", "High-street retail"]}
    for ptype, names in expected.items():
        p = copy.deepcopy(project)
        p.info.project_type = ptype
        assert [x.name for x in p.active_products()] == names
