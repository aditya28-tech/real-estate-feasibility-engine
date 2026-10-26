"""
stress_view.py  -  STEP 8b: the 'Stress & Monte Carlo' screen.

Figure builders are plain functions (testable); render_stress() draws the page in Streamlit.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from engine.inputs import from_dict
from engine.stress import (DEFAULT_STEPS, LEVERS, McRanges, headroom, monte_carlo, one_way, outcome, scenario_table,
                           tornado, two_way)

BLUE, GREEN, RED, ORANGE, NAVY = "#5B9BD5", "#70AD47", "#C00000", "#ED7D31", "#1F3864"
FMT = {"price": "{:+.0%}", "cost": "{:+.0%}", "speed": "{:.2f}x", "delay": "+{:d} Q"}


def _lay(fig, title, h=340):
    fig.update_layout(title=dict(text=title, x=0.01, font=dict(size=14)), height=h, margin=dict(l=10, r=10, t=45, b=10),
                      plot_bgcolor="white", legend=dict(orientation="h", y=-0.2))
    fig.update_yaxes(gridcolor="#EDEDED")
    return fig


def compute_tables(project) -> dict:
    """Everything that does not depend on the sliders (~150 model runs)."""
    return dict(
        scenarios=scenario_table(project),
        one_way={lv: one_way(project, lv) for lv in DEFAULT_STEPS},
        tornado=tornado(project),
        irr_grid=two_way(project, "cost", [0.0, 0.05, 0.10, 0.15, 0.20], "price", [-0.10, -0.05, 0.0, 0.05, 0.10], "developer_irr"),
        pat_grid=two_way(project, "cost", [0.0, 0.05, 0.10, 0.15, 0.20], "price", [-0.10, -0.05, 0.0, 0.05, 0.10], "pat"),
        peak_grid=two_way(project, "speed", [0.75, 1.0, 1.25, 1.5, 2.0], "delay", [0, 1, 2, 4], "peak"),
        headroom=headroom(project))


def fig_one_way(rows, lever, hurdle):
    x = [FMT[lever].format(int(r["value"]) if lever == "delay" else r["value"]) for r in rows]
    y = [r["developer_irr"] for r in rows]
    f = go.Figure(go.Scatter(x=x, y=y, mode="lines+markers+text", text=[f"{v:.0%}" if v is not None else "n/a" for v in y],
                             textposition="top center", line=dict(color=NAVY, width=3)))
    f.add_hline(y=hurdle, line_dash="dash", line_color=RED, annotation_text=f"hurdle {hurdle:.0%}")
    f.update_yaxes(tickformat=".0%")
    return _lay(f, LEVERS[lever], 280)


def fig_tornado(rows):
    labels = [r["lever"] + f"  ({FMT_KEY(r)})" for r in rows]
    f = go.Figure()
    f.add_bar(y=labels, x=[(r["down"] or 0) - r["base"] for r in rows], orientation="h", name="Downside", marker_color=RED,
              text=[f"{r['down']:.0%}" if r["down"] is not None else "n/a" for r in rows], textposition="outside")
    f.add_bar(y=labels, x=[(r["up"] or 0) - r["base"] for r in rows], orientation="h", name="Upside", marker_color=GREEN,
              text=[f"{r['up']:.0%}" if r["up"] is not None else "n/a" for r in rows], textposition="outside")
    f.update_layout(barmode="overlay"); f.update_xaxes(tickformat="+.0%", title="change in developer IRR vs base")
    return _lay(f, f"What moves developer IRR the most? (base {rows[0]['base']:.0%})", 320)


def FMT_KEY(r):
    lever = next(k for k, v in LEVERS.items() if v == r["lever"])
    show = lambda v: FMT[lever].format(int(v) if lever == "delay" else v)
    return f"{show(r['down_value'])} / {show(r['up_value'])}"


def fig_heat(grid, rows, cols, row_fmt, col_fmt, title, value_fmt, good_high=True, y_title="", x_title=""):
    f = px.imshow(grid, x=[col_fmt.format(c) for c in cols], y=[row_fmt.format(r) for r in rows], aspect="auto",
                  color_continuous_scale="RdYlGn" if good_high else "RdYlGn_r", text_auto=False)
    f.update_traces(text=[[value_fmt.format(v) for v in row] for row in grid], texttemplate="%{text}",
                    hovertemplate=f"{y_title} %{{y}} · {x_title} %{{x}}: %{{text}}<extra></extra>")
    f.update_layout(coloraxis_showscale=False); f.update_xaxes(title=x_title, side="top"); f.update_yaxes(title=y_title)
    return _lay(f, title, 320)


def fig_mc_hist(mc, threshold):
    irr = mc["irr"][~np.isnan(mc["irr"])]
    f = go.Figure(go.Histogram(x=irr, nbinsx=40, marker_color=BLUE, hovertemplate="IRR %{x:.0%}: %{y} runs<extra></extra>"))
    for v, lab, col in [(threshold, f"threshold {threshold:.0%}", RED), (mc["irr_p10"], "P10", ORANGE), (mc["irr_p50"], "P50", NAVY),
                        (mc["irr_p90"], "P90", GREEN)]:
        f.add_vline(x=v, line_dash="dash", line_color=col, annotation_text=lab, annotation_position="top")
    f.update_xaxes(tickformat=".0%", title="developer IRR"); f.update_yaxes(title="number of runs")
    return _lay(f, f"Developer IRR across {mc['n']:,} random scenarios", 360)


def fig_mc_exceedance(mc, threshold):
    irr = np.sort(mc["irr"][~np.isnan(mc["irr"])])
    prob = 1 - np.arange(len(irr)) / len(irr)
    f = go.Figure(go.Scatter(x=irr, y=prob, mode="lines", line=dict(color=NAVY, width=3),
                             hovertemplate="P(IRR ≥ %{x:.0%}) = %{y:.0%}<extra></extra>"))
    p_thr = float(np.mean(irr >= threshold)) if len(irr) else 0.0
    f.add_vline(x=threshold, line_dash="dash", line_color=RED)
    f.add_annotation(x=threshold, y=p_thr, text=f"{p_thr:.0%} chance ≥ {threshold:.0%}", showarrow=True, arrowhead=2)
    f.update_xaxes(tickformat=".0%", title="developer IRR at least …"); f.update_yaxes(tickformat=".0%", title="probability")
    return _lay(f, "Probability that developer IRR is at least X", 360)


def fig_mc_scatter(mc):
    f = go.Figure(go.Scatter(x=mc["peak"], y=mc["irr"], mode="markers", marker=dict(size=5, color=mc["samples"]["price"],
                  colorscale="RdYlGn", colorbar=dict(title="price<br>shock", tickformat=".0%"), opacity=0.7),
                  hovertemplate="peak ₹%{x:,.1f} Cr · IRR %{y:.0%}<extra></extra>"))
    f.update_xaxes(title="peak investment (₹ Cr)"); f.update_yaxes(tickformat=".0%", title="developer IRR")
    return _lay(f, "Return vs funding need for every run (colour = price shock)", 360)


def render_stress(P, fingerprint: str, tables_fn=None):
    """tables_fn(fingerprint) -> compute_tables result (the app passes a cached version)."""
    import streamlit as st
    cached = tables_fn or (lambda fp: compute_tables(from_dict(json.loads(fp))))

    st.header("Stress testing & Monte Carlo")
    st.caption("Levers act on top of the active scenario (page 1), exactly like the Excel STRESS sheet. Your inputs are never changed.")
    hurdle = P.finance.benchmarks["developer_irr"]

    # ---------- A. live sliders
    with st.container(border=True):
        st.subheader("A · Live what-if")
        c = st.columns(4)
        price = c[0].slider("Sales price shock", -30, 30, 0, 1, format="%d%%") / 100
        cost = c[1].slider("Construction cost shock", -10, 40, 0, 1, format="%d%%") / 100
        speed = c[2].slider("Sales period multiplier", 0.50, 2.50, 1.00, 0.05, format="%.2fx")
        delay = c[3].slider("Extra delay (quarters)", 0, 8, 0, 1)
        base, s = outcome(P), outcome(P, price=price, cost=cost, speed=speed, delay=delay)
        if not s["ok"]:
            st.warning("This combination breaks a model check (e.g. the project runs past 40 quarters): " + "; ".join(s["problems"][:2]))
        m = st.columns(5)
        pct = lambda v: "n/a" if v is None else f"{v:.1%}"
        dpp = lambda a, b: None if (a is None or b is None) else f"{(a - b) * 100:+.1f} pts"
        m[0].metric("Developer IRR", pct(s["developer_irr"]), dpp(s["developer_irr"], base["developer_irr"]))
        m[1].metric("Developer NPV", f"₹{s['developer_npv']:,.1f} Cr", f"{s['developer_npv'] - base['developer_npv']:+,.1f}")
        m[2].metric("PAT", f"₹{s['pat']:,.1f} Cr", f"{s['pat'] - base['pat']:+,.1f}")
        m[3].metric("Peak investment", f"₹{s['peak']:,.1f} Cr", f"{s['peak'] - base['peak']:+,.1f}", delta_color="inverse")
        m[4].metric("Payback", f"Q{s['payback_q']}" if s["payback_q"] else "never",
                    f"{(s['payback_q'] or 99) - (base['payback_q'] or 99):+d} qtrs" if s["payback_q"] and base["payback_q"] else None, delta_color="inverse")
        verdict = s["developer_irr"] is not None and s["developer_irr"] >= hurdle
        (st.success if verdict else st.error)(f"Developer IRR {'stays above' if verdict else 'falls below'} the {hurdle:.0%} hurdle in this case.")
        k = 32
        f = go.Figure()
        f.add_scatter(y=np.cumsum(base["developer_cf"])[:k], x=[f"Q{i}" for i in range(1, k + 1)], name="Base case", line=dict(color="#A5A5A5", width=3))
        f.add_scatter(y=np.cumsum(s["developer_cf"])[:k], x=[f"Q{i}" for i in range(1, k + 1)], name="Stressed", line=dict(color=RED, width=3))
        st.plotly_chart(_lay(f, "Developer cumulative cash (funding curve): base vs stressed (₹ Cr)", 320), width="stretch")

    T = cached(fingerprint)

    # ---------- B. scenarios + tornado
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("B · Scenario comparison")
        df = pd.DataFrame(T["scenarios"])[["scenario", "gdv", "ebitda", "pat", "developer_irr", "developer_npv", "peak", "payback_q"]]
        df.columns = ["Scenario", "GDV ₹Cr", "EBITDA ₹Cr", "PAT ₹Cr", "Developer IRR", "Dev NPV ₹Cr", "Peak ₹Cr", "Payback"]
        df["Developer IRR"] = df["Developer IRR"].map(lambda v: "n/a" if v is None else f"{v:.1%}")
        df["Payback"] = df["Payback"].map(lambda q: f"Q{q}" if q else "never")
        st.dataframe(df.round(1), hide_index=True, width="stretch")
    with c2:
        st.plotly_chart(fig_tornado(T["tornado"]), width="stretch")

    # ---------- C. one-way
    st.subheader("C · One lever at a time – developer IRR")
    cols = st.columns(4)
    for col, lv in zip(cols, DEFAULT_STEPS):
        col.plotly_chart(fig_one_way(T["one_way"][lv], lv, hurdle), width="stretch")
    with st.expander("Show the one-way tables (IRR, NPV, PAT, EBITDA, peak, payback)"):
        for lv in DEFAULT_STEPS:
            d = pd.DataFrame(T["one_way"][lv])[["value", "developer_irr", "developer_npv", "pat", "ebitda", "peak", "payback_q"]]
            d.columns = [LEVERS[lv], "Developer IRR", "Dev NPV ₹Cr", "PAT ₹Cr", "EBITDA ₹Cr", "Peak ₹Cr", "Payback Q"]
            st.dataframe(d.round(4), hide_index=True, width="stretch")

    # ---------- D. heat maps
    st.subheader("D · Two levers together – heat maps")
    h = st.columns(3)
    pr, co_, sp, dl = [-0.10, -0.05, 0.0, 0.05, 0.10], [0.0, 0.05, 0.10, 0.15, 0.20], [0.75, 1.0, 1.25, 1.5, 2.0], [0, 1, 2, 4]
    h[0].plotly_chart(fig_heat(T["irr_grid"], co_, pr, "{:+.0%}", "{:+.0%}", "Developer IRR: price × cost", "{:.0%}",
                               y_title="cost", x_title="price"), width="stretch")
    h[1].plotly_chart(fig_heat(T["pat_grid"], co_, pr, "{:+.0%}", "{:+.0%}", "PAT (₹ Cr): price × cost", "{:,.0f}",
                               y_title="cost", x_title="price"), width="stretch")
    h[2].plotly_chart(fig_heat(T["peak_grid"], sp, dl, "{:.2f}x", "+{} Q", "Peak investment (₹ Cr): speed × delay", "{:,.1f}",
                               good_high=False, y_title="speed", x_title="delay"), width="stretch")

    # ---------- E. headroom
    st.subheader("E · Headroom – how much can go wrong?")
    hr = T["headroom"]
    pct0 = lambda v: "beyond the tested range" if v is None else f"{v:+.1%}"
    e = st.columns(4)
    e[0].metric("Price shock → EBITDA = 0", pct0(hr["price_to_zero_ebitda"]))
    e[1].metric("Cost overrun → EBITDA = 0", pct0(hr["cost_to_zero_ebitda"]))
    e[2].metric(f"Price shock → IRR = {hurdle:.0%}", pct0(hr["price_to_hurdle"]))
    e[3].metric(f"Cost overrun → IRR = {hurdle:.0%}", pct0(hr["cost_to_hurdle"]))
    st.caption(("Sales speed: IRR stays above the hurdle up to 3.0x slower. " if hr["speed_to_hurdle"] is None
                else f"Sales speed: IRR reaches the hurdle at {hr['speed_to_hurdle']:.2f}x. ") +
               ("Delay: IRR stays above the hurdle for every delay the model can test (up to 12 quarters)." if hr["delay_to_hurdle"] is None
                else f"Delay: IRR falls below the hurdle at +{hr['delay_to_hurdle']} quarters."))

    # ---------- F. Monte Carlo
    st.subheader("F · Monte Carlo – probabilities instead of single answers")
    st.caption("Each run picks a random price shock, cost shock, sales speed and delay from the ranges below "
               "(triangular: lowest · most likely · highest), runs the full model, and records the results.")
    with st.form("mc_form"):
        r = McRanges()
        c = st.columns(3)
        def tri(col, label, t, scale, fmt):
            lo = col.number_input(f"{label} – lowest", value=t[0] * scale, format=fmt)
            ml = col.number_input(f"{label} – most likely", value=t[1] * scale, format=fmt)
            hi = col.number_input(f"{label} – highest", value=t[2] * scale, format=fmt)
            return (lo / scale, ml / scale, hi / scale)
        price_r = tri(c[0], "Price shock %", r.price, 100, "%.1f")
        cost_r = tri(c[1], "Cost shock %", r.cost, 100, "%.1f")
        speed_r = tri(c[2], "Sales period ×", r.speed, 1, "%.2f")
        st.write("Probability of an extra delay")
        d = st.columns(4)
        probs = {q: d[i].number_input(f"+{q} quarter(s) %", value=p * 100, min_value=0.0, max_value=100.0, step=5.0) / 100
                 for i, (q, p) in enumerate(r.delay_probs.items())}
        c = st.columns(3)
        n = c[0].selectbox("Number of runs", [250, 500, 1000, 2000], index=2)
        seed = int(c[1].number_input("Random seed (same seed = same answer)", value=42, step=1))
        go_ = c[2].form_submit_button("▶ Run Monte Carlo", type="primary")
    bad = [lab for lab, t in [("price", price_r), ("cost", cost_r), ("speed", speed_r)] if not (t[0] <= t[1] <= t[2])]
    if bad:
        st.error(f"For {', '.join(bad)}: lowest ≤ most likely ≤ highest is required.")
    elif sum(probs.values()) <= 0:
        st.error("Delay probabilities must add up to more than 0%.")
    elif go_:
        bar = st.progress(0.0, text="Running…")
        res = monte_carlo(P, McRanges(price_r, cost_r, speed_r, probs), n=n, seed=seed, progress=lambda x: bar.progress(x, text=f"Running… {x:.0%}"))
        bar.empty()
        st.session_state.mc = dict(fp=fingerprint, res=res)
    mc_state = st.session_state.get("mc")
    if mc_state:
        mc = mc_state["res"]
        if mc_state["fp"] != fingerprint:
            st.warning("These results were calculated before your latest input changes – press ▶ Run Monte Carlo again.")
        thr = st.slider("Show the probability of developer IRR being at least…", 0, 150, int(round(mc["hurdle"] * 100)), 1, format="%d%%") / 100
        irr_ok = mc["irr"][~np.isnan(mc["irr"])]
        p_thr = float(np.mean(irr_ok >= thr)) if len(irr_ok) else 0.0
        k = st.columns(4)
        k[0].metric(f"P(developer IRR ≥ {thr:.0%})", f"{p_thr:.1%}")
        k[1].metric("P(NPV > 0)", f"{mc['p_npv_positive']:.1%}")
        k[2].metric("P(loss: PAT < 0)", f"{mc['p_loss']:.1%}")
        k[3].metric("Peak investment P90", f"₹{mc['peak_p90']:,.1f} Cr", f"worst ₹{mc['peak_max']:,.1f} Cr", delta_color="off")
        st.info(f"In {mc['n']:,} random scenarios the developer IRR is between **{mc['irr_p10']:.0%}** (P10 – only 1 in 10 runs is worse) "
                f"and **{mc['irr_p90']:.0%}** (P90), with a median of **{mc['irr_p50']:.0%}**. "
                f"There is a **{p_thr:.0%}** chance it is at least {thr:.0%}." +
                (f" ({mc['failed_runs']} runs broke a model check.)" if mc["failed_runs"] else ""), icon="🎲")
        c1, c2 = st.columns(2)
        c1.plotly_chart(fig_mc_hist(mc, thr), width="stretch")
        c2.plotly_chart(fig_mc_exceedance(mc, thr), width="stretch")
        st.plotly_chart(fig_mc_scatter(mc), width="stretch")
        st.dataframe(pd.DataFrame({"": ["P10 (pessimistic)", "P50 (median)", "P90 (optimistic)"],
                                   "Developer IRR": [f"{mc['irr_p10']:.1%}", f"{mc['irr_p50']:.1%}", f"{mc['irr_p90']:.1%}"],
                                   "Developer NPV ₹Cr": [round(mc["npv_p10"], 1), round(mc["npv_p50"], 1), round(mc["npv_p90"], 1)],
                                   "PAT ₹Cr": [round(mc["pat_p10"], 1), round(mc["pat_p50"], 1), round(mc["pat_p90"], 1)]}),
                     hide_index=True)
