"""
engine/curves.py  -  STEP 2b: the CURVE engine (Python version of the Excel CURVES sheet).

It answers: HOW MUCH of each total falls in each quarter?  Every row is a list of 40 shares
that always adds up to exactly 100% (or 0% when the item is switched off).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .inputs import Project, CRORE, HORIZON_Q, MANUAL_CURVES, CONSTRUCTION_HEADS
from .timeline import Timeline


# ------------------------------------------------------------------ the five curve shapes
def curve_weights(name: str, n: int) -> np.ndarray:
    """Share of the total in each of n quarters (i = 1..n). Always sums to 1."""
    if n <= 0:
        return np.zeros(0)
    i = np.arange(1, n + 1, dtype=float)
    if name == "Upfront":
        w = (i == 1).astype(float)
    elif name == "Even":
        w = np.full(n, 1.0 / n)
    elif name == "Front-loaded":
        w = 2 * (n - i + 1) / (n * (n + 1))
    elif name == "Back-loaded":
        w = 2 * i / (n * (n + 1))
    elif name == "S-curve":                       # exact scaling: sum of sin((2i-1)x) = 1/sin(x), x = pi/2n
        w = np.sin(math.pi * (i - 0.5) / n) * math.sin(math.pi / (2 * n))
    else:
        raise ValueError(f"Unknown curve '{name}'")
    return w


def spread(name: str, start_q: int, end_q: int) -> np.ndarray:
    """Place a curve on the 40-quarter grid from start_q to end_q (inclusive)."""
    out = np.zeros(HORIZON_Q)
    lo, hi = max(start_q, 1), min(end_q, HORIZON_Q)
    if hi < lo:
        return out
    out[lo - 1:hi] = curve_weights(name, hi - lo + 1)          # window clipped to the model (as in Excel)
    return out


# ------------------------------------------------------------------ result container
@dataclass
class Curves:
    revenue: dict = field(default_factory=dict)           # product -> Rs Cr (after scenario price change)
    construction_cost: dict = field(default_factory=dict) # product -> Rs Cr (after scenario cost change)
    sales_pct: dict = field(default_factory=dict)         # product -> 40 shares
    cons_pct: dict = field(default_factory=dict)
    cons_cum: dict = field(default_factory=dict)          # cumulative construction progress (drives CLP)
    sales_profile: np.ndarray = None                      # all products, weighted by revenue
    cons_profile: np.ndarray = None                       # all products, weighted by construction cost
    category_profile: dict = field(default_factory=dict)  # category -> weighted construction profile
    cost_pct: dict = field(default_factory=dict)          # cost key -> 40 shares (None = Follow Collections)
    checks: list = field(default_factory=list)


def _weighted(arrays: dict, weights: dict, names) -> np.ndarray:
    total = sum(weights[n] for n in names)
    if total <= 0:
        return np.zeros(HORIZON_Q)
    return sum(weights[n] * arrays[n] for n in names) / total


def build_curves(project: Project, tl: Timeline) -> Curves:
    sc = project.scenario()
    cv = Curves()
    active = project.active_products()

    for p in active:                                            # per-product sales & construction %
        t = tl.products[p.name]
        cv.revenue[p.name] = p.area_sqft * p.rate * (1 + sc.price_change) / CRORE
        cv.construction_cost[p.name] = p.area_sqft * p.construction_rate * (1 + sc.cost_change) / CRORE
        cv.sales_pct[p.name] = spread(p.sales_curve, t.launch, t.sales_end)
        cv.cons_pct[p.name] = spread(p.construction_curve, t.cons_start, t.cons_end)
        cv.cons_cum[p.name] = np.cumsum(cv.cons_pct[p.name])

    names = [p.name for p in active]
    cv.sales_profile = _weighted(cv.sales_pct, cv.revenue, names)
    cv.cons_profile = _weighted(cv.cons_pct, cv.construction_cost, names)
    for _, _, cat in CONSTRUCTION_HEADS:
        cv.category_profile[cat] = _weighted(cv.cons_pct, cv.construction_cost, [p.name for p in active if p.category == cat])

    cat_of_head = {k: cat for k, _, cat in CONSTRUCTION_HEADS}
    for c in project.costs:                                     # every cost head
        curve = c.curve
        if c.key == "land":
            curve = "Follow Collections" if project.info.deal_type == "JV" else project.land.payment_curve
        if not c.applicable:
            cv.cost_pct[c.key] = np.zeros(HORIZON_Q)
        elif curve == "Follow Construction":
            cv.cost_pct[c.key] = cv.category_profile[cat_of_head[c.key]] if c.key in cat_of_head else cv.cons_profile
        elif curve == "Follow Sales":
            cv.cost_pct[c.key] = cv.sales_profile
        elif curve == "Follow Collections":
            cv.cost_pct[c.key] = None                           # filled by the collections engine (Step 3)
        elif curve == "Follow Project Life":
            cv.cost_pct[c.key] = spread("Even", 1, tl.last_q)
        elif curve == "At Project End":
            cv.cost_pct[c.key] = spread("Upfront", tl.last_q, tl.last_q)
        else:                                                   # Upfront / Even / Front / Back / S-curve
            s, e = tl.cost_windows[c.key]
            cv.cost_pct[c.key] = spread(curve, s, e)

    # checks: every active row must total 100%
    for n in names:
        for label, arr in (("sales", cv.sales_pct[n]), ("construction", cv.cons_pct[n])):
            if abs(arr.sum() - 1) > 1e-9:
                cv.checks.append(f"[Curves] '{n}' {label} % totals {arr.sum():.6f}, not 100%.")
    for k, arr in cv.cost_pct.items():
        c = project.cost(k)
        if arr is None or not c.applicable:
            continue
        if abs(arr.sum() - 1) > 1e-9 and arr.sum() != 0:
            cv.checks.append(f"[Curves] cost head '{c.name}' totals {arr.sum():.6f}, not 100%.")
    return cv
