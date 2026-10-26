"""
engine/cashflow.py  -  STEP 4b: CASH FLOW, P&L and RETURNS  (Excel CASHFLOW + OUTPUT sheets)

  * outflow of every cost head = amount x its quarterly % (from CURVES).
    In a JV the initial-investment items (stamp duty, brokerage, legal, BAR share, pre-DA development,
    pre-launch marketing) are paid early at their payout quarter and only the BALANCE follows the curve,
    so nothing is counted twice.
  * landowner (JV): the advance (token, DD, DA) is paid first; afterwards he receives nothing until his
    share of collections exceeds the advance  ->  cumulative paid = max(cumulative advance, cumulative share).
  * project cash flow (before landowner share) and developer cash flow (after it)
  * P&L, IRR, NPV, peak investment, break-even, payback, equity multiple, ROCE, CAGR, yearly (FY) summary
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .inputs import Project, HORIZON_Q, CONSTRUCTION_HEADS
from .timeline import Timeline
from .curves import Curves
from .collections import Collections
from .costs import CostResult

PULL = {"sd": "sd", "brok": "brok", "legal": "legal", "bar": "bar", "mkt": "marketing"}   # cost key -> initial item


# ------------------------------------------------------------------ IRR / NPV helpers
def npv(rate: float, flows: np.ndarray) -> float:
    """Excel NPV: first flow discounted one period."""
    t = np.arange(1, len(flows) + 1)
    return float(np.sum(flows / (1 + rate) ** t))


def irr(flows: np.ndarray):
    """Quarterly IRR by bisection (same root as Excel for normal 'invest first, earn later' flows).
    Returns None when the cash flow never changes sign."""
    flows = np.asarray(flows, dtype=float)
    if not (np.any(flows > 0) and np.any(flows < 0)):
        return None
    f = lambda r: np.sum(flows / (1 + r) ** np.arange(len(flows)))
    lo, hi = -0.99, 1.0
    while f(hi) > 0 and hi < 1e6:
        hi *= 2
    if f(lo) * f(hi) > 0:
        return None
    for _ in range(300):
        mid = (lo + hi) / 2
        if f(lo) * f(mid) <= 0: hi = mid
        else: lo = mid
    return (lo + hi) / 2


def _first_q(mask: np.ndarray):
    idx = np.flatnonzero(mask)
    return int(idx[0]) + 1 if idx.size else None


@dataclass
class CashFlow:
    inflow: np.ndarray = None
    outflows: dict = field(default_factory=dict)       # cost key -> 40 values (landowner share excluded)
    total_outflow: np.ndarray = None
    lo_advance: np.ndarray = None
    lo_paid: np.ndarray = None
    project_cf: np.ndarray = None
    developer_cf: np.ndarray = None
    tax: np.ndarray = None
    developer_cf_post_tax: np.ndarray = None
    pnl: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    fy_summary: dict = field(default_factory=dict)
    checks: list = field(default_factory=list)


def build_cashflow(project: Project, tl: Timeline, cv: Curves, co: Collections, cr: CostResult) -> CashFlow:
    cf = CashFlow()
    jv = project.info.deal_type == "JV"
    q_ = project.initial.payout_q
    A, items = cr.amounts, cr.initial_items
    cons_keys = {k for k, _, _ in CONSTRUCTION_HEADS}

    def at(q: int, amount: float) -> np.ndarray:
        v = np.zeros(HORIZON_Q)
        if 1 <= q <= HORIZON_Q: v[q - 1] = amount
        return v

    # ---------------- outflows by cost head
    cf.inflow = co.total.copy()
    for c in project.costs:
        k, G, pct = c.key, A[c.key], cv.cost_pct[c.key]
        if k == "land":
            cf.outflows[k] = np.zeros(HORIZON_Q) if jv else G * pct
        elif k in PULL:
            pa = items[PULL[k]] if jv else 0.0
            cf.outflows[k] = at(q_[PULL[k]], pa) + (G - pa) * pct
            if pa < -1e-9 or pa > G + 1e-9:
                cf.checks.append(f"[Cash flow] early payment for '{c.name}' exceeds its cost head.")
        elif k in cons_keys:
            pa = items["dev"] * G / cr.construction_heads_total if (jv and cr.construction_heads_total > 0) else 0.0
            cf.outflows[k] = at(q_["dev"], pa) + (G - pa) * pct
        else:
            cf.outflows[k] = G * pct
    cf.total_outflow = sum(cf.outflows.values())

    # ---------------- landowner: advance first, then recovered from his share
    if jv:
        cf.lo_advance = at(q_["token"], items["token"]) + at(q_["dd"], items["dd"]) + at(q_["da"], items["da"])
    else:
        cf.lo_advance = np.zeros(HORIZON_Q)
    paid_cum = np.maximum(np.cumsum(cf.lo_advance), np.cumsum(co.landowner))
    cf.lo_paid = np.diff(np.concatenate([[0.0], paid_cum]))

    # ---------------- net cash flows
    cf.project_cf = cf.inflow - cf.total_outflow
    cf.developer_cf = cf.project_cf - cf.lo_paid

    # ---------------- P&L (Excel OUTPUT sections A–D)
    rev, cost = cr.total_revenue, cr.total_cost
    ebitda = rev - cost
    tax_rate = project.finance.tax_llp if project.info.entity == "LLP" else project.finance.tax_company
    tax = max(0.0, ebitda) * tax_rate
    pat = ebitda - tax
    dev_rev = rev * cr.dev_share
    cf.pnl = dict(revenue=rev, total_cost=cost, ebitda=ebitda, ebitda_margin=ebitda / rev if rev else 0.0,
                  tax_rate=tax_rate, tax=tax, pat=pat, pat_margin=pat / rev if rev else 0.0,
                  developer_revenue=dev_rev, developer_cost=dev_rev - ebitda,
                  ebitda_margin_on_dev_share=ebitda / dev_rev if dev_rev else 0.0,
                  landowner_revenue=rev - dev_rev, construction_heads_total=cr.construction_heads_total)
    cf.tax = tax * co.profile
    cf.developer_cf_post_tax = cf.developer_cf - cf.tax

    # ---------------- returns & funding metrics (Excel CASHFLOW section E + OUTPUT section E)
    qrate = (1 + project.finance.cost_of_equity) ** 0.25 - 1
    annual = lambda q: None if q is None else (1 + q) ** 4 - 1
    p_irr_q, d_irr_q = irr(cf.project_cf), irr(cf.developer_cf)
    cum_d = np.cumsum(cf.developer_cf)
    peak = max(0.0, -cum_d.min())
    peak_q = int(np.argmin(cum_d)) + 1 if peak > 0 else None
    running_min = np.minimum.accumulate(cum_d)
    payback_q = _first_q((cum_d >= -1e-6) & (running_min < -1e-6))
    life = project.info.lifecycle_override_years or tl.last_q / 4
    ii = cr.initial_used
    land_heads = A["land"] + A["sd"] + A["brok"]
    em = (dev_rev / (cost - land_heads) if (cost - land_heads) else 0.0) if jv else (rev / cost if cost else 0.0)
    roce = ebitda / ii / life if ii > 0 and life > 0 else 0.0
    roi = pat + ii
    cagr = (roi / ii) ** (1 / life) - 1 if ii > 0 and life > 0 and roi > 0 else 0.0
    pos, neg = cf.developer_cf[cf.developer_cf > 0].sum(), -cf.developer_cf[cf.developer_cf < 0].sum()
    cf.metrics = dict(
        project_irr=annual(p_irr_q), developer_irr=annual(d_irr_q),
        developer_irr_post_tax=annual(irr(cf.developer_cf_post_tax)),
        project_npv=npv(qrate, cf.project_cf), developer_npv=npv(qrate, cf.developer_cf),
        peak_investment=peak, peak_quarter=peak_q, peak_date=tl.end_dates[peak_q - 1] if peak_q else None,
        largest_quarter_deficit=max(0.0, -cf.developer_cf.min()),
        breakeven_project_q=_first_q(cf.project_cf > 1e-6), breakeven_developer_q=_first_q(cf.developer_cf > 1e-6),
        payback_q=payback_q, payback_date=tl.end_dates[payback_q - 1] if payback_q else None,
        cash_multiple=pos / neg if neg else 0.0, equity_multiple=em, initial_investment=ii, lifecycle_years=life,
        roce=roce, return_on_investment=roi, cagr=cagr, pat_margin=cf.pnl["pat_margin"], ebitda_margin=cf.pnl["ebitda_margin"],
        land_cost_to_gdv=A["land"] / rev if rev else 0.0, initial_investment_to_gdv=ii / rev if rev else 0.0)

    # benchmark status (green = beats benchmark)
    bm = project.finance.benchmarks
    pairs = {"project_irr": "project_irr", "developer_irr": "developer_irr", "equity_multiple": "equity_multiple",
             "roce": "roce", "cagr": "cagr", "pat_margin": "pat_margin", "ebitda_margin": "ebitda_margin"}
    cf.metrics["status"] = {k: ("Strong" if cf.metrics[k] is not None and cf.metrics[k] > bm[b] else "Review")
                            for k, b in pairs.items()}

    # ---------------- yearly summary by Indian financial year
    for i, fy in enumerate(tl.fy):
        s = cf.fy_summary.setdefault(fy, dict(collections=0.0, costs_paid=0.0, paid_to_landowner=0.0, developer_net=0.0))
        s["collections"] += cf.inflow[i]; s["costs_paid"] += cf.total_outflow[i]
        s["paid_to_landowner"] += cf.lo_paid[i]; s["developer_net"] += cf.developer_cf[i]

    # ---------------- checks (same as Excel CASHFLOW section H)
    for c in project.costs:
        expected = 0.0 if (jv and c.key == "land") else A[c.key]
        if abs(cf.outflows[c.key].sum() - expected) > 1e-6:
            cf.checks.append(f"[Cash flow] '{c.name}' paid {cf.outflows[c.key].sum():.4f} instead of {expected:.4f}.")
    if jv and (abs(cf.lo_paid.sum() - co.landowner.sum()) > 1e-6):
        cf.checks.append("[Cash flow] landowner not paid exactly his share (advance not fully recovered).")
    if abs(cf.developer_cf.sum() - ebitda) > 1e-6:
        cf.checks.append("[Cash flow] developer total cash does not equal EBITDA.")
    if abs(cf.tax.sum() - tax) > 1e-6:
        cf.checks.append("[Cash flow] tax spread does not equal P&L tax.")
    return cf


def run_model(project: Project) -> dict:
    """One call that runs the whole engine in order and returns every result."""
    from .inputs import validate
    from .timeline import build_timeline
    from .curves import build_curves
    from .collections import build_collections
    from .costs import build_costs
    tl = build_timeline(project)
    cv = build_curves(project, tl)
    co = build_collections(project, tl, cv)
    cr = build_costs(project, cv)
    cf = build_cashflow(project, tl, cv, co, cr)
    problems = validate(project) + tl.errors + cv.checks + co.checks + cr.checks + cf.checks
    return dict(timeline=tl, curves=cv, collections=co, costs=cr, cashflow=cf, problems=problems)
