"""
engine/costs.py  -  STEP 4a: HOW MUCH does each cost head cost?  (Excel INPUTS Sections 2, 6 and 7)

  * land section: land value, land cost / landowner share, stamp duty, brokerage base
  * all 21 cost heads (+ spare rows) with the exact Excel calculation for each
  * calculators: BAR / premium FAR, AIF interest, initial investment (JV and Outright)
All amounts in Rs Crore.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .inputs import Project, CRORE, SQM_PER_SQYD, SQFT_PER_SQYD, CONSTRUCTION_HEADS, COMPOUNDING
from .curves import Curves


@dataclass
class CostResult:
    total_sa: float = 0.0                 # total saleable area of active products (sq ft)
    total_revenue: float = 0.0            # GDV (Rs Cr)
    total_construction: float = 0.0       # sum of product construction cost (Rs Cr)
    plotted_revenue: float = 0.0
    land_value_market: float = 0.0
    land_value_purchase: float = 0.0
    land_cost: float = 0.0                # JV: landowner revenue share | Outright: purchase price
    stamp_duty: float = 0.0
    brokerage_base: float = 0.0
    dev_share: float = 1.0
    amounts: dict = field(default_factory=dict)        # cost key -> Rs Cr
    total_cost: float = 0.0
    construction_heads_total: float = 0.0
    bar: dict = field(default_factory=dict)            # BAR calculator details
    aif: dict = field(default_factory=dict)
    initial_items: dict = field(default_factory=dict)  # JV initial-investment items (Rs Cr)
    initial_jv: float = 0.0
    initial_outright: float = 0.0
    initial_used: float = 0.0
    checks: list = field(default_factory=list)


def build_costs(project: Project, cv: Curves) -> CostResult:
    r = CostResult()
    L, info = project.land, project.info
    jv = info.deal_type == "JV"
    active = project.active_products()

    r.total_sa = sum(p.area_sqft for p in active)
    r.total_revenue = sum(cv.revenue.values())
    r.total_construction = sum(cv.construction_cost.values())
    r.plotted_revenue = sum(cv.revenue[p.name] for p in active if p.zone == "Plotted Development")
    rev_cat = lambda cat: sum(cv.revenue[p.name] for p in active if p.category == cat)
    con_cat = lambda cat: sum(cv.construction_cost[p.name] for p in active if p.category == cat)

    # ---------------- land section
    dlc_sqyd = L.dlc_rate_sqm * SQM_PER_SQYD
    r.land_value_market = L.area_sqyd * L.market_rate / CRORE
    r.land_value_purchase = L.area_sqyd * L.purchase_rate / CRORE
    r.dev_share = (1 - L.lo_share) if jv else 1.0
    r.land_cost = L.lo_share * r.total_revenue if jv else r.land_value_purchase
    r.stamp_duty = (L.area_sqyd * dlc_sqyd * L.stamp_duty_jv if jv
                    else L.area_sqyd * max(dlc_sqyd, L.purchase_rate) * L.stamp_duty_outright) / CRORE
    r.brokerage_base = r.land_value_market if jv else r.land_value_purchase

    # ---------------- BAR / premium FAR calculator
    b = project.bar
    free = L.area_sqyd * SQM_PER_SQYD * b.free_far
    planned = r.total_sa * (SQM_PER_SQYD / SQFT_PER_SQYD) / b.loading_factor if b.loading_factor > 0 else 0.0
    extra = max(0.0, planned - free)
    pct = (b.pct_table.get(b.land_use, {}) or {}).get(b.authority) or 0.0
    bar_cost = extra * b.reserved_price_sqm * pct / CRORE
    r.bar = dict(free_sqm=free, planned_sqm=planned, extra_sqm=extra, pct=pct, cost_excl_gst=bar_cost,
                 cost=bar_cost * (1 + (b.gst_rate if b.gst_applicable else 0.0)))

    # ---------------- cost heads (same formulas as Excel Section 6)
    A = r.amounts
    cat_of = {k: cat for k, _, cat in CONSTRUCTION_HEADS}
    gate = lambda c, v: v if c.applicable else 0.0
    order = [c.key for c in project.costs]
    for c in project.costs:                                  # first pass: everything except contingency & AIF
        k = c.key
        if k == "land":    A[k] = r.land_cost
        elif k == "sd":    A[k] = r.stamp_duty
        elif k == "brok":  A[k] = gate(c, c.rate1 * r.brokerage_base)
        elif k in cat_of:  A[k] = gate(c, con_cat(cat_of[k]))
        elif k == "ovh":   A[k] = gate(c, c.rate1 * r.total_revenue)
        elif k == "mkt":   A[k] = gate(c, c.rate1 * (r.total_revenue - r.plotted_revenue) + c.rate2 * r.plotted_revenue)
        elif k == "legal": A[k] = gate(c, c.rate1 * r.total_sa / CRORE)
        elif k == "ews":   A[k] = gate(c, c.rate1 * c.rate2 * r.total_sa / CRORE)
        elif k == "edc":
            v = {"Rs/sq ft (total saleable area)": c.rate1 * r.total_sa / CRORE,
                 "% of construction cost": c.rate1 * r.total_construction, "Lump sum (Rs Cr)": c.rate1}.get(c.rate2, 0.0)
            A[k] = gate(c, v)
        elif k == "hotel": A[k] = gate(c, c.rate1 * c.rate2 / CRORE)
        elif k == "furn":  A[k] = gate(c, c.rate1 * sum(p.area_sqft for p in active if p.category == "Studio") / CRORE)
        elif k == "gst":   A[k] = gate(c, (rev_cat("Commercial") + rev_cat("Plot")) * c.rate2 * c.rate1 * r.dev_share)
        elif k == "bar":   A[k] = gate(c, r.bar["cost"])
        elif k.startswith("spare"):
            v = {"Rs/sq ft (total saleable area)": (c.rate1 or 0) * r.total_sa / CRORE,
                 "% of total revenue": (c.rate1 or 0) * r.total_revenue,
                 "% of construction cost": (c.rate1 or 0) * r.total_construction,
                 "Lump sum (Rs Cr)": c.rate1 or 0,
                 "Rs/sq yd (land area)": (c.rate1 or 0) * L.area_sqyd / CRORE}.get(c.basis, 0.0)
            A[k] = gate(c, v)
    # AIF: interest on (land + stamp duty + brokerage)
    a = project.aif
    principal = A["land"] + A["sd"] + A.get("brok", 0.0)
    m = COMPOUNDING.get(a.compounding, 1)
    aif_cost = principal * ((1 + a.rate / m) ** (m * a.tenure_years) - 1)
    r.aif = dict(principal=principal, periods_per_year=m, cost=aif_cost)
    A["aif"] = gate(project.cost("aif"), aif_cost)
    # contingency: % of construction cost OR of all costs except land, stamp duty, brokerage and itself
    c = project.cost("cont")
    base_all = sum(v for k, v in A.items() if k not in ("land", "sd", "brok", "cont"))
    A["cont"] = gate(c, c.rate1 * (r.total_construction if c.rate2 == "Construction cost" else base_all))

    r.amounts = {k: A[k] for k in order}                    # keep the Excel order
    r.total_cost = sum(r.amounts.values())
    r.construction_heads_total = sum(A[k] for k in cat_of)

    # ---------------- initial investment
    ii = project.initial
    advance = ii.advance_pct * r.land_value_market
    r.initial_items = {
        "token": advance - ii.dd_amount - ii.da_amount, "dd": ii.dd_amount, "da": ii.da_amount,
        "legal": A["legal"] * ii.legal_share, "dev": ii.dev_cost_pre_da, "marketing": ii.marketing_pre_launch,
        "sd": A["sd"], "brok": A["brok"], "bar": A["bar"] * ii.bar_share}
    r.initial_jv = sum(r.initial_items.values())
    r.initial_outright = (A["land"] + A["sd"] + A["brok"]
                          + ii.outright_construction_share * (A["villa"] + A["apt"] + A["studio"])
                          + ii.outright_legal_share * A["legal"])
    r.initial_used = r.initial_jv if jv else r.initial_outright

    # ---------------- checks
    if abs(r.construction_heads_total - r.total_construction) > 1e-6 and all(project.cost(k).applicable for k in cat_of):
        r.checks.append("[Costs] construction heads do not add up to the product construction cost.")
    if r.initial_items["token"] < -1e-9:
        r.checks.append("[Costs] DD + DA instalments exceed the total landowner advance.")
    if project.cost("bar").applicable and pct == 0:
        r.checks.append(f"[Costs] no BAR % for {b.authority} / {b.land_use}.")
    return r
