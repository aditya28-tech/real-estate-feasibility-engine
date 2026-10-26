"""
engine/timeline.py  -  STEP 2a: the TIMELINE engine (Python version of the Excel TIMELINE sheet).

It answers one question: WHEN does everything happen?
  * a calendar of 40 quarters (dates, financial year, project year)
  * for every active product: launch, sales end, construction start and construction end
    (after scenario delay, sales-speed multiplier and links between products)
  * the project's last active quarter and a phase label for every quarter
  * for every cost head: the window (start..end quarter) in which it may be spent
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

from .inputs import Project, HORIZON_Q, MANUAL_CURVES

# ------------------------------------------------------------------ calendar helpers
def quarter_end(start: date, q: int) -> date:
    """End date of quarter q (q = 1 is the quarter ending on the project start date)."""
    months = start.month - 1 + 3 * (q - 1)
    y, m = start.year + months // 12, months % 12 + 1
    nxt = date(y + (m == 12), m % 12 + 1, 1)          # first day of the following month
    return nxt - timedelta(days=1)


def fy_label(d: date) -> str:
    """Indian financial year (April-March), e.g. 30-Jun-2027 -> 'FY 2027-28'."""
    fy_end = d.year + (1 if d.month > 3 else 0)
    return f"FY {fy_end - 1}-{str(fy_end)[-2:]}"


# ------------------------------------------------------------------ result containers
@dataclass
class ProductTiming:
    name: str
    launch: int            # first selling quarter
    sales_end: int         # last selling quarter
    cons_start: int        # first construction quarter
    cons_end: int          # last construction quarter
    sales_n: int           # number of selling quarters
    cons_n: int            # number of construction quarters
    note: str = ""         # plain-English explanation (like Excel Section 5B)


@dataclass
class Timeline:
    quarters: list                                  # [1, 2, ... 40]
    end_dates: list
    start_dates: list
    fy: list
    project_year: list
    products: dict = field(default_factory=dict)    # name -> ProductTiming (active products only)
    last_q: int = 0
    phase: list = field(default_factory=list)
    cost_windows: dict = field(default_factory=dict)  # cost key -> (start, end) or None
    errors: list = field(default_factory=list)


# ------------------------------------------------------------------ product timing (Section 5B logic)
def _event_quarter(t: ProductTiming, duration_input: int, event: str) -> int:
    return {"Launch": t.launch, "Sales end": t.sales_end, "Construction start": t.cons_start,
            "Construction 50%": t.cons_start + math.ceil(duration_input / 2) - 1,
            "Construction end": t.cons_end}[event]


def _offset_text(n: int) -> str:
    return f"{abs(n)} qtr(s) before " if n < 0 else f"{n} qtr(s) after "


def resolve_products(project: Project) -> tuple[dict, list]:
    """Final quarters for every active product, processed top-down so links only point upwards."""
    sc = project.scenario()
    active_names = {p.name for p in project.active_products()}
    resolved, errors = {}, []
    for p in project.products:
        if p.name not in active_names:
            continue
        tm = p.timing
        dur_in = {x.name: x.construction_duration_q for x in project.products}

        def linked(prod, event, offset, fixed_q, label):
            if prod in resolved:                                   # anchor is above AND active
                return _event_quarter(resolved[prod], dur_in[prod], event) + offset, \
                       f"{_offset_text(offset)}{prod} – {event.lower()}"
            return fixed_q + sc.delay_q, f"fixed fallback – {prod} not active"

        # construction start: computed first unless it depends on our own launch
        cons_pre, cons_txt = None, ""
        if tm.cons_mode == "Fixed quarter":
            cons_pre, cons_txt = p.construction_start_q + sc.delay_q, "fixed"
        elif tm.cons_mode == "Linked to another product":
            cons_pre, cons_txt = linked(tm.cons_link_product, tm.cons_link_event, tm.cons_offset, p.construction_start_q, "construction")

        if tm.launch_mode == "Fixed quarter":
            launch, l_txt = p.launch_q + sc.delay_q, "fixed"
        elif tm.launch_mode == "Linked to another product":
            launch, l_txt = linked(tm.launch_link_product, tm.launch_link_event, tm.launch_offset, p.launch_q, "launch")
        else:                                                      # After own construction start
            launch, l_txt = cons_pre + tm.launch_offset, _offset_text(tm.launch_offset) + "own construction start"

        if tm.cons_mode == "After own launch":
            cons_start, cons_txt = launch + tm.cons_offset, _offset_text(tm.cons_offset) + "own launch"
        else:
            cons_start = cons_pre

        sales_n = max(1, math.ceil(p.sales_period_q * sc.sales_period_mult - 1e-9))
        t = ProductTiming(p.name, launch, launch + sales_n - 1, cons_start,
                          cons_start + p.construction_duration_q - 1, sales_n, p.construction_duration_q,
                          f"Launch Q{launch} ({l_txt})  |  Construction Q{cons_start} ({cons_txt})")
        if t.launch < 1 or t.cons_start < 1:
            errors.append(f"[Timing] '{p.name}': launch / construction start falls before Q1.")
        if t.sales_end > HORIZON_Q or t.cons_end > HORIZON_Q:
            errors.append(f"[Timing] '{p.name}': runs beyond Q{HORIZON_Q} (the model horizon).")
        resolved[p.name] = t
    return resolved, errors


# ------------------------------------------------------------------ the full timeline
def build_timeline(project: Project) -> Timeline:
    start = project.info.start_date
    qs = list(range(1, HORIZON_Q + 1))
    ends = [quarter_end(start, q) for q in qs]
    tl = Timeline(quarters=qs, end_dates=ends,
                  start_dates=[quarter_end(start, q - 1) + timedelta(days=1) for q in qs],
                  fy=[fy_label(d) for d in ends], project_year=[f"Y{math.ceil(q / 4)}" for q in qs])

    tl.products, tl.errors = resolve_products(project)
    pts = list(tl.products.values())
    tl.last_q = max([max(t.sales_end, t.cons_end) for t in pts], default=0)
    first_launch = min([t.launch for t in pts], default=0)

    for q in qs:                                                   # phase label per quarter
        selling = any(t.launch <= q <= t.sales_end for t in pts)
        building = any(t.cons_start <= q <= t.cons_end for t in pts)
        if q > tl.last_q:          ph = "Post-project"
        elif selling and building: ph = "Sales + Constr."
        elif selling:              ph = "Sales"
        elif building:             ph = "Construction"
        elif q < first_launch:     ph = "Pre-launch"
        else:                      ph = "Completion / handover"
        tl.phase.append(ph)

    land = project.land
    for c in project.costs:                                        # cost-head spending windows
        curve, s, e = c.curve, c.start_q, c.end_q
        if c.key == "land":                                        # land follows the deal type
            if project.info.deal_type == "JV":
                curve = "Follow Collections"
            else:
                curve, s, e = land.payment_curve, land.payment_start_q, land.payment_end_q
        if not c.applicable:
            tl.cost_windows[c.key] = None
        elif curve in MANUAL_CURVES:
            tl.cost_windows[c.key] = (s, s if curve == "Upfront" else e)
        elif curve == "Follow Project Life":
            tl.cost_windows[c.key] = (1, tl.last_q)
        elif curve == "At Project End":
            tl.cost_windows[c.key] = (tl.last_q, tl.last_q)
        else:                                                      # Follow Construction / Sales / Collections
            tl.cost_windows[c.key] = None
    return tl


def gantt_text(tl: Timeline, quarters: int = 24) -> str:
    """Simple text Gantt: S = selling, C = construction, # = both, . = nothing."""
    lines = ["Quarter".ljust(28) + "".join(f"{q:>3}" for q in range(1, quarters + 1))]
    for t in tl.products.values():
        row = ""
        for q in range(1, quarters + 1):
            s, c = t.launch <= q <= t.sales_end, t.cons_start <= q <= t.cons_end
            row += "  #" if s and c else "  S" if s else "  C" if c else "  ."
        lines.append(t.name[:27].ljust(28) + row)
    return "\n".join(lines)
