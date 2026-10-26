"""
dashboard.py  -  STEP 7b: the DASHBOARD screen (KPI cards, takeaways, interactive charts).

`charts(project, res)` builds every Plotly figure (testable without a screen);
`render_dashboard(project, res)` draws the page inside the Streamlit app.
"""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from engine.inputs import CONSTRUCTION_HEADS
from engine.report import key_metrics_table, kpi_cards, takeaways
from engine.timeline import quarter_end

BLUE, GREEN, RED, ORANGE, GREY, NAVY = "#5B9BD5", "#70AD47", "#C00000", "#ED7D31", "#A5A5A5", "#1F3864"
STATUS_STYLE = {"good": ("#E2F0D9", "#548235"), "review": ("#FFF2CC", "#BF8F00"), "neutral": ("#F2F5FA", NAVY)}


def _layout(fig, title, height=380):
    fig.update_layout(title=dict(text=title, x=0.01, font=dict(size=15)), height=height, margin=dict(l=10, r=10, t=50, b=10),
                      legend=dict(orientation="h", y=-0.15), plot_bgcolor="white", hovermode="x unified")
    fig.update_xaxes(showgrid=False); fig.update_yaxes(gridcolor="#EDEDED")
    return fig


def charts(project, res) -> dict:
    tl, cv, co, cr, cf = res["timeline"], res["curves"], res["collections"], res["costs"], res["cashflow"]
    n = max(tl.last_q, 4) + 1
    Q = [f"Q{q}" for q in range(1, min(n, 40) + 1)]
    k = len(Q)
    figs = {}

    # 1. developer cash flow + funding curve
    dcf = cf.developer_cf[:k]; cum = np.cumsum(cf.developer_cf)[:k]
    f = go.Figure()
    f.add_bar(x=Q, y=dcf, name="Net cash flow (quarter)", marker_color=[RED if v < 0 else BLUE for v in dcf],
              hovertemplate="%{x}: ₹%{y:,.1f} Cr<extra></extra>")
    f.add_scatter(x=Q, y=cum, name="Cumulative = funding curve", line=dict(color=ORANGE, width=3),
                  hovertemplate="cumulative ₹%{y:,.1f} Cr<extra></extra>")
    m = cf.metrics
    if m["peak_quarter"]:
        f.add_annotation(x=f"Q{m['peak_quarter']}", y=-m["peak_investment"], text=f"Peak ₹{m['peak_investment']:,.1f} Cr",
                         showarrow=True, arrowhead=2, ay=40)
    if m["payback_q"] and m["payback_q"] <= k:
        f.add_annotation(x=f"Q{m['payback_q']}", y=cum[m["payback_q"] - 1], text="Payback", showarrow=True, arrowhead=2, ay=-40)
    figs["cashflow"] = _layout(f, "Developer cash flow (₹ Cr) and funding curve", 420)

    # 2. cost breakdown (grouped)
    A = cr.amounts
    groups = {"Land / landowner share": A["land"] + A["sd"] + A["brok"],
              "Construction": sum(A[key] for key, _, _ in CONSTRUCTION_HEADS),
              "Marketing & sales": A["mkt"], "Corporate overheads": A["ovh"], "Approvals, legal & BAR": A["legal"] + A["bar"]}
    groups["Other (EWS, contingency, EDC, GST, AIF …)"] = cr.total_cost - sum(groups.values())
    g = pd.Series(groups).sort_values()
    f = go.Figure(go.Bar(x=g.values, y=g.index, orientation="h", marker_color=NAVY, text=[f"₹{v:,.1f} Cr" for v in g.values],
                         textposition="outside", hovertemplate="%{y}: ₹%{x:,.1f} Cr<extra></extra>"))
    figs["costs"] = _layout(f, f"Cost breakdown – total ₹{cr.total_cost:,.1f} Cr", 380)
    figs["costs"].update_layout(hovermode="closest")

    # 3. revenue mix by product
    rev = pd.Series(cv.revenue).sort_values(ascending=False)
    f = go.Figure(go.Pie(labels=rev.index, values=rev.values, hole=0.55, textinfo="label+percent",
                         hovertemplate="%{label}: ₹%{value:,.1f} Cr<extra></extra>"))
    f.update_layout(annotations=[dict(text=f"₹{rev.sum():,.0f} Cr<br>GDV", showarrow=False, font=dict(size=16))], showlegend=False)
    figs["revenue"] = _layout(f, "Revenue mix by product", 380)

    # 4. cash by financial year
    fy = pd.DataFrame(cf.fy_summary).T
    fy = fy[fy.abs().sum(axis=1) > 1e-9]
    f = go.Figure()
    for col, name, colr in [("collections", "Collections", GREEN), ("costs_paid", "Costs paid", RED), ("paid_to_landowner", "Paid to landowner", GREY)]:
        f.add_bar(x=fy.index, y=fy[col], name=name, marker_color=colr, hovertemplate=name + ": ₹%{y:,.1f} Cr<extra></extra>")
    f.add_scatter(x=fy.index, y=fy["developer_net"], name="Developer net", mode="lines+markers", line=dict(color=NAVY, width=3))
    figs["fy"] = _layout(f, "Cash by financial year (₹ Cr)", 380)

    # 5. bookings vs collections + receivables
    bookings = sum(co.bookings.values())[:k]
    f = go.Figure()
    f.add_bar(x=Q, y=bookings, name="Bookings (sales value)", marker_color="#A9D08E")
    f.add_bar(x=Q, y=co.total[:k], name="Cash collected", marker_color=BLUE)
    f.add_scatter(x=Q, y=(np.cumsum(sum(co.bookings.values())) - np.cumsum(co.total))[:k], name="Receivables (sold, not yet paid)",
                  line=dict(color=RED, dash="dot"))
    figs["collections"] = _layout(f, "Bookings vs cash collected (₹ Cr)", 380)

    # 6. cumulative cash in vs out
    f = go.Figure()
    f.add_scatter(x=Q, y=np.cumsum(cf.inflow)[:k], name="Cumulative collections", line=dict(color=GREEN, width=3), fill="tozeroy",
                  fillcolor="rgba(112,173,71,0.12)")
    f.add_scatter(x=Q, y=np.cumsum(cf.total_outflow + cf.lo_paid)[:k], name="Cumulative cash out (costs + landowner)",
                  line=dict(color=RED, width=3))
    figs["cumulative"] = _layout(f, "Cumulative cash in vs cash out (₹ Cr) – the gap is profit building up", 380)

    # 7. Gantt
    start = project.info.start_date
    rows = []
    for t in tl.products.values():
        rows.append(dict(Product=t.name, Activity="Selling", Start=quarter_end(start, t.launch - 1) + timedelta(days=1), End=quarter_end(start, t.sales_end)))
        rows.append(dict(Product=t.name, Activity="Construction", Start=quarter_end(start, t.cons_start - 1) + timedelta(days=1), End=quarter_end(start, t.cons_end)))
    f = px.timeline(pd.DataFrame(rows), x_start="Start", x_end="End", y="Product", color="Activity",
                    color_discrete_map={"Selling": GREEN, "Construction": BLUE})
    f.update_yaxes(autorange="reversed"); f.update_layout(barmode="group")
    figs["gantt"] = _layout(f, "Project timeline (selling & construction)", 340)
    figs["gantt"].update_layout(hovermode="closest")
    return figs


def _card_html(c) -> str:
    bg, fg = STATUS_STYLE[c["status"]]
    return (f"<div style='background:{bg};border-radius:10px;padding:10px 14px;margin-bottom:12px;border-top:4px solid {fg};'>"
            f"<div style='font-size:12px;color:#595959;font-weight:600'>{c['label']}</div>"
            f"<div style='font-size:26px;font-weight:700;color:{fg};line-height:1.25'>{c['value']}</div>"
            f"<div style='font-size:11px;color:#595959'>{c['sub']}</div></div>")


def render_dashboard(project, res):
    import streamlit as st
    info = project.info
    st.markdown(f"## {info.name} — Feasibility dashboard")
    tl = res["timeline"]
    st.caption(f"{info.location} · {info.project_type} · {info.deal_type} deal · scenario: **{info.scenario}** · "
               f"{project.land.area_sqyd / 4840:,.1f} acres · {res['costs'].total_sa:,.0f} sq ft saleable · "
               f"{info.start_date:%b %Y} – {tl.end_dates[tl.last_q - 1]:%b %Y}" if tl.last_q else "")
    if res["problems"]:
        st.error(f"✖ {len(res['problems'])} check(s) failed – results may be wrong. See '9 · Checks & summary'.")
    else:
        st.success("✔ ALL CHECKS PASSED")

    cards = kpi_cards(project, res)
    for row in range(3):
        cols = st.columns(4)
        for col, c in zip(cols, cards[row * 4:(row + 1) * 4]):
            col.markdown(_card_html(c), unsafe_allow_html=True)
    st.caption("Green = beats the benchmark (page 8) · amber = review · blue = information")

    with st.container(border=True):
        st.markdown("#### 📝 Key takeaways (written automatically from the model)")
        for i, t in enumerate(takeaways(project, res), 1):
            st.markdown(f"**{i}.** {t}")

    figs = charts(project, res)
    t1, t2, t3, t4 = st.tabs(["💰 Cash flow & funding", "🧱 Costs & revenue", "🏦 Collections", "📅 Timeline"])
    with t1:
        st.plotly_chart(figs["cashflow"], width="stretch")
        c1, c2 = st.columns(2)
        c1.plotly_chart(figs["fy"], width="stretch")
        c2.plotly_chart(figs["cumulative"], width="stretch")
    with t2:
        c1, c2 = st.columns(2)
        c1.plotly_chart(figs["costs"], width="stretch")
        c2.plotly_chart(figs["revenue"], width="stretch")
        pnl = res["cashflow"].pnl
        st.dataframe(pd.DataFrame([["Revenue", pnl["revenue"]], ["Total cost", pnl["total_cost"]], ["EBITDA", pnl["ebitda"]],
                                   [f"Tax ({pnl['tax_rate']:.1%})", pnl["tax"]], ["PAT", pnl["pat"]]],
                                  columns=["P&L", "₹ Crore"]).round(2), hide_index=True)
    with t3:
        st.plotly_chart(figs["collections"], width="stretch")
        st.dataframe(pd.DataFrame([{"Product": s.product, "Milestone": s.name, "% of sale": f"{s.pct:.1%}", "Falls due": s.text}
                                   for s in res["collections"].schedule]), hide_index=True, width="stretch", height=300)
    with t4:
        st.plotly_chart(figs["gantt"], width="stretch")
        st.dataframe(pd.DataFrame([{"Product": t.name, "How it was decided": t.note} for t in tl.products.values()]),
                     hide_index=True, width="stretch")
    with st.expander("📋 All 18 key metrics (same as the Excel OUTPUT sheet)"):
        df = pd.DataFrame(key_metrics_table(project, res))
        st.dataframe(df.rename(columns=str.title), hide_index=True, width="stretch")
