"""
engine/stress.py  -  STEP 8: stress testing and Monte Carlo (Excel STRESS sheet, and beyond).

Four levers act ON TOP of the active scenario (exactly like the Excel STRESS levers):
    price  : sales price shock      (-0.10 = all prices 10% lower)
    cost   : construction cost shock (+0.10 = construction 10% dearer)
    speed  : sales period multiplier (1.5 = every product takes 50% longer to sell)
    delay  : extra quarters added to every FIXED launch / construction start (linked products inherit it)

Functions
    stressed(project, ...)            -> a stressed COPY of the project (the original is never changed)
    outcome(project, ...)             -> headline results of one stressed run
    scenario_table / one_way / two_way / tornado / headroom
    monte_carlo(project, ranges, n)   -> n random combinations of the four levers -> probabilities
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

import numpy as np

from .inputs import Project, Scenario
from .cashflow import run_model

LEVERS = {"price": "Sales price shock", "cost": "Construction cost shock", "speed": "Sales period multiplier", "delay": "Extra delay (quarters)"}
NEUTRAL = dict(price=0.0, cost=0.0, speed=1.0, delay=0)


def stressed(project: Project, price=0.0, cost=0.0, speed=1.0, delay=0, scenario: str | None = None) -> Project:
    """Copy of the project whose active scenario is combined with the levers (same maths as Excel)."""
    p = copy.deepcopy(project)
    if scenario:
        p.info.scenario = scenario
    s = p.scenario()
    combined = Scenario(f"{s.name} (stressed)", s.sales_period_mult * speed, (1 + s.price_change) * (1 + price) - 1,
                        (1 + s.cost_change) * (1 + cost) - 1, int(s.delay_q + delay))
    p.scenarios = [x for x in p.scenarios if x.name != combined.name] + [combined]
    p.info.scenario = combined.name
    return p


def outcome(project: Project, **levers) -> dict:
    r = run_model(stressed(project, **levers))
    m, pnl = r["cashflow"].metrics, r["cashflow"].pnl
    return dict(gdv=pnl["revenue"], total_cost=pnl["total_cost"], ebitda=pnl["ebitda"], pat=pnl["pat"],
                pat_margin=pnl["pat_margin"], developer_irr=m["developer_irr"], project_irr=m["project_irr"],
                developer_npv=m["developer_npv"], peak=m["peak_investment"], payback_q=m["payback_q"],
                equity_multiple=m["equity_multiple"], ok=not r["problems"], problems=r["problems"],
                developer_cf=r["cashflow"].developer_cf)


def scenario_table(project: Project) -> list:
    return [dict(scenario=s.name, **{k: v for k, v in outcome(project, scenario=s.name).items() if k != "developer_cf"})
            for s in project.scenarios]


DEFAULT_STEPS = {"price": [-0.15, -0.10, -0.05, 0.0, 0.05, 0.10, 0.15], "cost": [-0.05, 0.0, 0.05, 0.10, 0.15, 0.20],
                 "speed": [0.75, 1.0, 1.25, 1.5, 2.0], "delay": [0, 1, 2, 3, 4, 6]}


def one_way(project: Project, lever: str, values=None) -> list:
    return [dict(value=v, **{k: x for k, x in outcome(project, **{lever: v}).items() if k != "developer_cf"})
            for v in (values or DEFAULT_STEPS[lever])]


def two_way(project: Project, row_lever: str, row_values, col_lever: str, col_values, metric: str) -> np.ndarray:
    grid = np.full((len(row_values), len(col_values)), np.nan)
    for i, rv in enumerate(row_values):
        for j, cv_ in enumerate(col_values):
            v = outcome(project, **{row_lever: rv, col_lever: cv_})[metric]
            grid[i, j] = np.nan if v is None else v
    return grid


def tornado(project: Project, metric="developer_irr", shocks=None) -> list:
    """Downside and upside of each lever on one metric, sorted by size of the downside."""
    shocks = shocks or {"price": (-0.10, 0.10), "cost": (0.10, -0.05), "speed": (1.5, 0.75), "delay": (2, 0)}
    base = outcome(project)[metric]
    rows = []
    for lever, (down, up) in shocks.items():
        d, u = outcome(project, **{lever: down})[metric], outcome(project, **{lever: up})[metric]
        rows.append(dict(lever=LEVERS[lever], down_value=down, up_value=up, base=base, down=d, up=u,
                         impact=(d - base) if (d is not None and base is not None) else float("nan")))
    return sorted(rows, key=lambda x: x["impact"])


def _bisect(f, lo, hi, iters=60):
    """Root of a function that changes sign between lo and hi (None if it does not)."""
    flo, fhi = f(lo), f(hi)
    if flo is None or fhi is None or flo * fhi > 0:
        return None
    for _ in range(iters):
        mid = (lo + hi) / 2
        fm = f(mid)
        if fm is None: return None
        if flo * fm <= 0: hi, fhi = mid, fm
        else: lo, flo = mid, fm
    return (lo + hi) / 2


def headroom(project: Project) -> dict:
    """How far each lever can move before profit disappears or IRR falls to the hurdle."""
    hurdle = project.finance.benchmarks["developer_irr"]
    base_e = outcome(project)["ebitda"]
    e_p = outcome(project, price=-0.15)["ebitda"]
    e_c = outcome(project, cost=0.20)["ebitda"]
    irr_gap = lambda **k: (lambda v: None if v is None else v - hurdle)(outcome(project, **k)["developer_irr"])
    def irr_ok(**k):
        o = outcome(project, **k)
        return o["ok"], o["developer_irr"]
    delay_q = None
    for d in range(0, 13):                                   # first delay (in quarters) that pushes IRR below the hurdle
        ok, v = irr_ok(delay=d)
        if not ok: break
        if v is None or v < hurdle: delay_q = d; break
    speed_gap = lambda x: (lambda r: None if (not r[0] or r[1] is None) else r[1] - hurdle)(irr_ok(speed=x))
    return dict(
        price_to_zero_ebitda=-base_e / ((base_e - e_p) / 0.15) if base_e != e_p else None,      # exact: EBITDA is linear in price
        cost_to_zero_ebitda=base_e / ((base_e - e_c) / 0.20) if base_e != e_c else None,        # exact: linear in construction cost
        price_to_hurdle=_bisect(lambda x: irr_gap(price=x), -0.9, 0.0),
        cost_to_hurdle=_bisect(lambda x: irr_gap(cost=x), 0.0, 5.0),
        speed_to_hurdle=_bisect(speed_gap, 1.0, 3.0),
        delay_to_hurdle=delay_q, hurdle=hurdle)


# ------------------------------------------------------------------------------------- Monte Carlo
@dataclass
class McRanges:
    """Triangular ranges (lowest, most likely, highest) for each lever + probabilities for delay."""
    price: tuple = (-0.15, 0.0, 0.08)
    cost: tuple = (-0.05, 0.03, 0.20)
    speed: tuple = (0.8, 1.0, 1.8)
    delay_probs: dict = field(default_factory=lambda: {0: 0.50, 1: 0.25, 2: 0.15, 3: 0.10})


def monte_carlo(project: Project, ranges: McRanges | None = None, n: int = 1000, seed: int = 42, progress=None) -> dict:
    ranges = ranges or McRanges()
    rng = np.random.default_rng(seed)
    tri = lambda t: rng.triangular(t[0], t[1], t[2], n) if t[0] < t[2] else np.full(n, t[1])
    price, cost, speed = tri(ranges.price), tri(ranges.cost), tri(ranges.speed)
    d_vals, d_p = np.array(list(ranges.delay_probs)), np.array(list(ranges.delay_probs.values()), dtype=float)
    delay = rng.choice(d_vals, size=n, p=d_p / d_p.sum())
    irr, npv_, peak, pat = (np.full(n, np.nan) for _ in range(4))
    failed = 0
    for i in range(n):
        o = outcome(project, price=float(price[i]), cost=float(cost[i]), speed=float(speed[i]), delay=int(delay[i]))
        if not o["ok"]:
            failed += 1
        irr[i] = np.nan if o["developer_irr"] is None else o["developer_irr"]
        npv_[i], peak[i], pat[i] = o["developer_npv"], o["peak"], o["pat"]
        if progress and i % max(1, n // 50) == 0:
            progress(i / n)
    hurdle = project.finance.benchmarks["developer_irr"]
    valid = ~np.isnan(irr)
    pct = lambda a, q: float(np.nanpercentile(a, q))
    return dict(
        n=n, seed=seed, failed_runs=failed, samples=dict(price=price, cost=cost, speed=speed, delay=delay),
        irr=irr, npv=npv_, peak=peak, pat=pat, hurdle=hurdle,
        p_irr_above_hurdle=float(np.mean(irr[valid] >= hurdle)) if valid.any() else 0.0,
        p_npv_positive=float(np.mean(npv_ > 0)), p_loss=float(np.mean(pat < 0)),
        irr_p10=pct(irr, 10), irr_p50=pct(irr, 50), irr_p90=pct(irr, 90),
        npv_p10=pct(npv_, 10), npv_p50=pct(npv_, 50), npv_p90=pct(npv_, 90),
        peak_p50=pct(peak, 50), peak_p90=pct(peak, 90), peak_max=float(np.nanmax(peak)),
        pat_p10=pct(pat, 10), pat_p50=pct(pat, 50), pat_p90=pct(pat, 90))
