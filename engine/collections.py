"""
engine/collections.py  -  STEP 3: the COLLECTIONS engine (Python version of the Excel COLLECTIONS sheet).

Bookings  ->  payment-plan (CLP) milestones  ->  cash actually received.

Rules (same as Excel):
  * Bookings in quarter t = product revenue x sales % in t.
  * Booking-linked milestone ("Booking + k quarters"): every buyer pays it k quarters after booking.
  * Construction-linked milestone ("Construction x% complete"): it falls due in the first quarter Q in which
    the product's cumulative construction progress reaches x%.
        - buyers who booked early enough pay it in quarter Q;
        - later buyers have missed it, so they pay it as a CATCH-UP, `catch_up_lag` quarters after booking.
    Formula for quarter t:  t < Q -> 0 ;  t = Q -> pct x (all bookings up to t - lag) ;  t > Q -> pct x bookings(t - lag)
  * JV: the landowner gets his revenue share of every rupee collected.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .inputs import Project, HORIZON_Q
from .timeline import Timeline
from .curves import Curves

TOL = 1e-9


@dataclass
class MilestoneDue:
    product: str
    plan: str
    name: str
    trigger: str
    value: float
    pct: float
    due_q: int | None          # construction-linked: quarter it falls due (None for booking-linked)
    text: str                  # plain English


@dataclass
class Collections:
    bookings: dict = field(default_factory=dict)          # product -> 40 values (Rs Cr)
    booking_linked: dict = field(default_factory=dict)    # product -> cash from booking-linked milestones
    construction_linked: dict = field(default_factory=dict)
    collections: dict = field(default_factory=dict)       # product -> total cash received per quarter
    receivables: dict = field(default_factory=dict)       # product -> booked but not yet paid (cumulative)
    schedule: list = field(default_factory=list)          # list of MilestoneDue
    total: np.ndarray = None
    landowner: np.ndarray = None
    developer: np.ndarray = None
    profile: np.ndarray = None                            # share of total collections per quarter
    checks: list = field(default_factory=list)


def _shift(arr: np.ndarray, k: int) -> np.ndarray:
    """Value of arr k quarters earlier (zeros before Q1)."""
    out = np.zeros_like(arr)
    if k == 0:
        return arr.copy()
    if k < len(arr):
        out[k:] = arr[:-k]
    return out


def trigger_quarter(cons_cum: np.ndarray, x: float, cons_start: int) -> int:
    """First quarter in which cumulative construction >= x (never before construction starts)."""
    q = int(np.sum(cons_cum < x - TOL)) + 1
    return max(q, cons_start)


def build_collections(project: Project, tl: Timeline, cv: Curves) -> Collections:
    co = Collections()
    lag = project.catch_up_lag
    qs = np.arange(1, HORIZON_Q + 1)

    for p in project.active_products():
        t = tl.products[p.name]
        B = cv.revenue[p.name] * cv.sales_pct[p.name]                  # bookings
        CB = np.cumsum(B)                                              # cumulative bookings
        B_lag, CB_lag = _shift(B, lag), _shift(CB, lag)
        book, cons = np.zeros(HORIZON_Q), np.zeros(HORIZON_Q)
        plan = project.plan(p.clp_plan)
        for m in plan.milestones:
            if m.pct == 0:
                continue
            if m.trigger == "Booking + quarters":
                book += m.pct * _shift(B, int(m.value))
                text = "at booking" if m.value == 0 else f"{int(m.value)} qtr(s) after booking"
                co.schedule.append(MilestoneDue(p.name, plan.name, m.name, m.trigger, m.value, m.pct, None, text))
            else:
                Q = trigger_quarter(cv.cons_cum[p.name], m.value, t.cons_start)
                cons += m.pct * np.where(qs < Q, 0.0, np.where(qs == Q, CB_lag, B_lag))
                text = (f"construction {m.value:.0%} reached in Q{Q}" if Q <= HORIZON_Q else "NOT REACHED in model")
                co.schedule.append(MilestoneDue(p.name, plan.name, m.name, m.trigger, m.value, m.pct, Q, text))
                if Q > HORIZON_Q:
                    co.checks.append(f"[Collections] '{p.name}': milestone '{m.name}' is never reached inside the model.")
        co.bookings[p.name] = B
        co.booking_linked[p.name] = book
        co.construction_linked[p.name] = cons
        co.collections[p.name] = book + cons
        co.receivables[p.name] = CB - np.cumsum(book + cons)

        rev = cv.revenue[p.name]                                       # product checks
        if abs(B.sum() - rev) > 1e-6 or abs((book + cons).sum() - rev) > 1e-6:
            co.checks.append(f"[Collections] '{p.name}': bookings {B.sum():.4f} / collections {(book + cons).sum():.4f} "
                             f"do not both equal revenue {rev:.4f} (cash lost beyond the horizon or plan not 100%).")
        if co.receivables[p.name].min() < -1e-6:
            co.checks.append(f"[Collections] '{p.name}': cash collected before it was booked.")

    co.total = sum(co.collections.values()) if co.collections else np.zeros(HORIZON_Q)
    lo_share = project.land.lo_share if project.info.deal_type == "JV" else 0.0
    co.landowner = co.total * lo_share
    co.developer = co.total - co.landowner
    tot = co.total.sum()
    co.profile = co.total / tot if tot > 0 else np.zeros(HORIZON_Q)

    # complete every cost head that follows collections (e.g. the JV landowner share)
    for c in project.costs:
        if cv.cost_pct.get(c.key) is None:
            cv.cost_pct[c.key] = co.profile.copy() if c.applicable else np.zeros(HORIZON_Q)

    if abs(tot - sum(cv.revenue.values())) > 1e-6:
        co.checks.append("[Collections] total collections do not equal total revenue.")
    return co


def verify_by_cohorts(project: Project, tl: Timeline, cv: Curves, co: Collections) -> float:
    """Independent second method: follow every booking quarter (cohort) of buyers one by one.
    Returns the largest difference against the fast engine above (should be ~0)."""
    lag, worst = project.catch_up_lag, 0.0
    for p in project.active_products():
        t = tl.products[p.name]
        cash = np.zeros(HORIZON_Q + 60)
        for b in range(1, HORIZON_Q + 1):
            booked = cv.revenue[p.name] * cv.sales_pct[p.name][b - 1]
            if booked == 0:
                continue
            for m in project.plan(p.clp_plan).milestones:
                if m.trigger == "Booking + quarters":
                    due = b + int(m.value)
                else:
                    due = max(trigger_quarter(cv.cons_cum[p.name], m.value, t.cons_start), b + lag)
                cash[due] += booked * m.pct
        worst = max(worst, float(np.abs(cash[1:HORIZON_Q + 1] - co.collections[p.name]).max()))
    return worst
