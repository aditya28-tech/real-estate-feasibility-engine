"""
engine/report.py  -  STEP 7a: the words and numbers behind the dashboard (pure Python, no screens).

  * kpi_cards(project, res)  -> 12 cards: label, value text, small text, status ("good" / "review" / "neutral")
  * takeaways(project, res)  -> plain-English sentences that rewrite themselves when the inputs change
  * key_metrics_table(project, res) -> the 18 OUTPUT metrics with benchmark and status
Kept separate from the screens so it can be tested automatically.
"""
from __future__ import annotations

from .inputs import CRORE, Project


def _pct(v, d=1):
    return "n/a" if v is None else f"{v:.{d}%}"


def _cr(v, d=1):
    return f"₹{v:,.{d}f} Cr"


def _q(q):
    return f"Q{q}" if q else "never"


def kpi_cards(project: Project, res: dict) -> list:
    cf, cr = res["cashflow"], res["costs"]
    pnl, m, bm = cf.pnl, cf.metrics, project.finance.benchmarks
    beats = lambda v, b: "neutral" if b is None else ("good" if (v is not None and v > b) else "review")
    sa = cr.total_sa or 1
    return [
        dict(label="GDV (total revenue)", value=_cr(pnl["revenue"]), sub=f"₹{pnl['revenue'] * CRORE / sa:,.0f} per sq ft", status="neutral"),
        dict(label="Total cost", value=_cr(pnl["total_cost"]), sub=f"{pnl['total_cost'] / pnl['revenue']:.1%} of GDV" if pnl["revenue"] else "", status="neutral"),
        dict(label="EBITDA", value=_cr(pnl["ebitda"]), sub=f"{pnl['ebitda_margin']:.1%} margin · target {bm['ebitda_margin']:.0%}",
             status=beats(pnl["ebitda_margin"], bm["ebitda_margin"])),
        dict(label="PAT", value=_cr(pnl["pat"]), sub=f"{pnl['pat_margin']:.1%} margin · tax {pnl['tax_rate']:.1%}",
             status=beats(pnl["pat_margin"], bm["pat_margin"])),
        dict(label="Developer IRR (pre-tax)", value=_pct(m["developer_irr"]), sub=f"target {bm['developer_irr']:.0%} · post-tax ≈ {_pct(m['developer_irr_post_tax'], 0)}",
             status=beats(m["developer_irr"], bm["developer_irr"])),
        dict(label="Project IRR", value=_pct(m["project_irr"]), sub=f"target {bm['project_irr']:.0%} · before landowner share",
             status=beats(m["project_irr"], bm["project_irr"])),
        dict(label="Developer NPV", value=_cr(m["developer_npv"]), sub=f"at {project.finance.cost_of_equity:.0%} cost of equity",
             status="good" if m["developer_npv"] > 0 else "review"),
        dict(label="Equity multiple", value=f"{m['equity_multiple']:.2f}x", sub=f"target {bm['equity_multiple']:.1f}x · cash multiple {m['cash_multiple']:.1f}x",
             status=beats(m["equity_multiple"], bm["equity_multiple"])),
        dict(label="Peak investment", value=_cr(m["peak_investment"]),
             sub=f"reached in {_q(m['peak_quarter'])}" + (f" ({m['peak_date']:%b %Y})" if m["peak_date"] else ""), status="neutral"),
        dict(label="Payback (developer)", value=_q(m["payback_q"]),
             sub=(f"{m['payback_date']:%b %Y} · first +ve quarter {_q(m['breakeven_developer_q'])}" if m["payback_date"] else "cash never recovered"),
             status="neutral" if m["payback_q"] else "review"),
        dict(label="ROCE (annualised)", value=_pct(m["roce"]), sub=f"target {bm['roce']:.0%} · on initial investment", status=beats(m["roce"], bm["roce"])),
        dict(label="CAGR", value=_pct(m["cagr"]), sub=f"target {bm['cagr']:.0%} · over {m['lifecycle_years']:.1f} yrs", status=beats(m["cagr"], bm["cagr"])),
    ]


def takeaways(project: Project, res: dict) -> list:
    cf, cr, co = res["cashflow"], res["costs"], res["collections"]
    pnl, m, bm, L = cf.pnl, cf.metrics, project.finance.benchmarks, project.land
    out = [
        f"The project generates {_cr(pnl['revenue'], 0)} of revenue against {_cr(pnl['total_cost'], 0)} of cost – "
        f"EBITDA {_cr(pnl['ebitda'], 0)} ({pnl['ebitda_margin']:.1%}) and PAT {_cr(pnl['pat'], 0)} ({pnl['pat_margin']:.1%}).",
    ]
    irr_ = m["developer_irr"]
    verdict = "comfortably above" if irr_ is not None and irr_ > 2 * bm["developer_irr"] else \
              "above" if irr_ is not None and irr_ > bm["developer_irr"] else "below"
    out.append(f"The developer earns a pre-tax IRR of {_pct(irr_, 0)} – {verdict} the {bm['developer_irr']:.0%} hurdle – "
               f"with an NPV of {_cr(m['developer_npv'])} at the {project.finance.cost_of_equity:.0%} cost of equity.")
    peak_txt = f"Maximum funding needed is {_cr(m['peak_investment'])} ({_q(m['peak_quarter'])})"
    if m["payback_q"]:
        peak_txt += f"; the developer gets all of it back by {_q(m['payback_q'])} ({m['payback_date']:%b %Y})"
    else:
        peak_txt += "; the money is never fully recovered inside the model"
    if project.info.deal_type == "JV":
        peak_txt += " – construction is largely funded by customer collections."
    else:
        peak_txt += " – most of this peak is the land payment, made before customer collections build up."
    out.append(peak_txt)
    if project.info.deal_type == "JV":
        lo_px = cr.land_cost * CRORE / L.area_sqyd if L.area_sqyd else 0
        uplift = lo_px / L.market_rate - 1 if L.market_rate else 0
        advance = project.initial.advance_pct * cr.land_value_market
        out.append(f"The landowner receives {_cr(cr.land_cost)} ({L.lo_share:.0%} revenue share) – about ₹{lo_px:,.0f} per sq yd, "
                   f"{uplift:+.0%} vs today's market rate – paid out of collections after his {_cr(advance)} advance is recovered.")
    else:
        out.append(f"Outright deal: land of {_cr(cr.land_cost)} is paid as per the land payment schedule ({L.payment_curve}).")
    beaten = [k for k, s in m["status"].items() if s == "Strong"]
    review = [k.replace("_", " ") for k, s in m["status"].items() if s != "Strong"]
    out.append(f"{len(beaten)} of {len(m['status'])} benchmarks are beaten" +
               (f"; review: {', '.join(review)}." if review else " – every benchmark is met."))
    q50 = next((i + 1 for i, v in enumerate(co.total.cumsum()) if v >= 0.5 * co.total.sum()), None)
    biggest = max(((k, v) for k, v in cr.amounts.items() if k != "land"), key=lambda kv: kv[1], default=(None, 0))
    name = project.cost(biggest[0]).name if biggest[0] else ""
    out.append(f"Half of all customer cash is in by {_q(q50)}; the largest cost after land is '{name}' at {_cr(biggest[1])} "
               f"({biggest[1] / pnl['revenue']:.1%} of GDV).")
    return out


def key_metrics_table(project: Project, res: dict) -> list:
    m, bm = res["cashflow"].metrics, project.finance.benchmarks
    rows = [
        ("Project IRR", _pct(m["project_irr"]), f"{bm['project_irr']:.0%}", m["status"]["project_irr"]),
        ("Developer IRR (pre-tax)", _pct(m["developer_irr"]), f"{bm['developer_irr']:.0%}", m["status"]["developer_irr"]),
        ("Equity multiple", f"{m['equity_multiple']:.2f}x", f"{bm['equity_multiple']:.1f}x", m["status"]["equity_multiple"]),
        ("ROCE (annualised)", _pct(m["roce"]), f"{bm['roce']:.0%}", m["status"]["roce"]),
        ("CAGR", _pct(m["cagr"]), f"{bm['cagr']:.0%}", m["status"]["cagr"]),
        ("PAT margin", _pct(m["pat_margin"]), f"{bm['pat_margin']:.0%}", m["status"]["pat_margin"]),
        ("EBITDA margin", _pct(m["ebitda_margin"]), f"{bm['ebitda_margin']:.0%}", m["status"]["ebitda_margin"]),
        ("Peak investment", _cr(m["peak_investment"], 2), "", ""),
        ("Land cost to GDV", _pct(m["land_cost_to_gdv"]), "", ""),
        ("Initial investment to GDV", _pct(m["initial_investment_to_gdv"]), "", ""),
        ("Break-even quarter (project)", _q(m["breakeven_project_q"]), "", ""),
        ("Break-even quarter (developer)", _q(m["breakeven_developer_q"]), "", ""),
        ("Payback quarter (developer)", _q(m["payback_q"]), "", ""),
        ("Project NPV @ cost of equity", _cr(m["project_npv"], 2), "", ""),
        ("Developer NPV @ cost of equity", _cr(m["developer_npv"], 2), "", ""),
        ("Developer IRR (post-tax, indicative)", _pct(m["developer_irr_post_tax"]), "", ""),
        ("Largest single-quarter deficit", _cr(m["largest_quarter_deficit"], 2), "", ""),
        ("Cash multiple (developer)", f"{m['cash_multiple']:.2f}x", "", ""),
    ]
    return [dict(metric=a, value=b, benchmark=c, status=d) for a, b, c, d in rows]
