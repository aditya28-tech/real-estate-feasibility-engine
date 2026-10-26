"""
app.py  -  STEP 6: the input screens of the Real Estate Feasibility Engine (Streamlit).

Run with:   streamlit run app.py
Every screen edits ONE Project object kept in memory (st.session_state). After every change the whole
engine re-runs (a fraction of a second), and any problem is shown right next to the field / row that caused it.
"""
from __future__ import annotations

import copy
import json
from datetime import date

import pandas as pd
import streamlit as st

from engine.inputs import (
    BAR_AUTHORITIES, BAR_LAND_USES, BASIC_CURVES, CATEGORIES, COMPOUNDING, CONS_MODES, CONSTRUCTION_HEADS,
    CONTINGENCY_BASES, COST_CURVES, CRORE, DEAL_TYPES, EDC_BASES, ENTITIES, HORIZON_Q, LAND_CURVES, LAUNCH_MODES,
    LINK_EVENTS, PROJECT_TYPES, SPARE_BASES, SQFT_PER_SQYD, SQYD_PER_ACRE, SQYD_PER_BIGHA, TRIGGERS, ZONES,
    CostHead, ClpPlan, Milestone, Product, Scenario, Timing, check_inputs, from_dict, sample_project, to_dict,
)
from engine.cashflow import run_model
from dashboard import render_dashboard
from stress_view import compute_tables, render_stress
from engine.export import build_excel_report, project_from_excel

st.set_page_config(page_title="Real Estate Feasibility Engine", page_icon="🏗️", layout="wide")

# ============================================================================ state & engine run
if "project" not in st.session_state:
    st.session_state.project = sample_project()
P = st.session_state.project


def rerun_after_edit(editor_key: str):
    """Commit pattern for editable tables: the project is already updated -> clear the table's edit
    memory and redraw everything from the project."""
    st.session_state.pop(editor_key, None)
    st.rerun()


FINGERPRINT = json.dumps(to_dict(P), sort_keys=True, default=str)   # project state used for this run's results


@st.cache_data(show_spinner="Running the stress tables (about 150 model runs)…", max_entries=8)
def stress_tables(fp: str):
    """Stress tables for one project state – shared by the stress screen and the Excel report."""
    return compute_tables(from_dict(json.loads(fp)))
issues = check_inputs(P)
try:
    RES = run_model(P)
except Exception as exc:                      # an unforeseen input combination – never crash the screens
    RES, ENGINE_ERROR = None, str(exc)
else:
    ENGINE_ERROR = ""

PAGE_SECTIONS = {
    "0 · Dashboard": [],
    "S · Stress & Monte Carlo": [],
    "1 · Project & land": ["Project", "Land"],
    "2 · Scenarios & zones": ["Scenarios", "Zones"],
    "3 · Products": ["Products"],
    "4 · Product timing": ["Timing"],
    "5 · Cost heads": ["Costs"],
    "6 · Calculators": ["BAR", "AIF", "Initial investment"],
    "7 · Payment plans": ["CLP"],
    "8 · Tax & benchmarks": ["Finance"],
    "9 · Checks & summary": [],
}


def issues_for(section: str, item: str | None = None) -> list:
    return [i for i in issues if i.section == section and (item is None or i.item == item)]


def show(section: str, item: str):
    """Show the error(s) for one field directly under it."""
    for i in issues_for(section, item):
        st.error(i.message, icon="⚠️")


def row_status(section: str, item: str) -> str:
    msgs = [i.message.split(": ", 1)[-1] for i in issues_for(section, item)]
    return "✔" if not msgs else "⚠ " + " | ".join(msgs)


def pct_in(label, value, key=None, help=None, max_value=100.0, step=0.25):
    """Percentage field: shown as 32 (%) but stored as 0.32."""
    return st.number_input(label, value=round(float(value) * 100, 6), min_value=-100.0, max_value=max_value,
                           step=step, format="%.2f", key=key, help=help) / 100


# ============================================================================ sidebar
with st.sidebar:
    st.title("🏗️ Feasibility Engine")
    st.caption(f"{P.info.name} · {P.info.project_type} · {P.info.deal_type} · {P.info.scenario}")
    labels = []
    for page, secs in PAGE_SECTIONS.items():
        n = sum(1 for i in issues if i.section in secs)
        labels.append(f"{page}  ⚠️ {n}" if n else page)
    choice = st.radio("Go to", labels, label_visibility="collapsed")
    page = choice.split("  ⚠️")[0]

    st.divider()
    engine_problems = RES["problems"] if RES else []
    if not issues and RES and not engine_problems:
        st.success("✔ ALL CHECKS PASSED")
    else:
        n_problems = len(issues) + sum(1 for p in engine_problems if not any(p.endswith(i.message) for i in issues))
        st.error(f"✖ {n_problems or 1} issue(s) – see page 9")
    if RES:
        m, pnl = RES["cashflow"].metrics, RES["cashflow"].pnl
        c1, c2 = st.columns(2)
        c1.metric("GDV", f"₹{pnl['revenue']:,.0f} Cr")
        c2.metric("EBITDA", f"{pnl['ebitda_margin']:.1%}")
        c1.metric("Developer IRR", "n/a" if m["developer_irr"] is None else f"{m['developer_irr']:.1%}")
        c2.metric("Peak funding", f"₹{m['peak_investment']:,.1f} Cr")
        st.caption(f"Payback: {'Q' + str(m['payback_q']) if m['payback_q'] else 'never'} · "
                   f"PAT ₹{pnl['pat']:,.1f} Cr · {RES['timeline'].last_q} quarters")

    st.divider()
    st.markdown("**📊 Excel report**")
    inc_stress = st.checkbox("Include stress tests (+ ~2 s)", value=True)
    mc_now = st.session_state.get("mc")
    mc_ok = bool(mc_now and mc_now["fp"] == FINGERPRINT)
    st.caption("Monte Carlo: " + ("included (latest run)" if mc_ok else "not included – run it on 'S · Stress & Monte Carlo' first"))
    if st.button("Build Excel report", width="stretch", disabled=RES is None):
        with st.spinner("Building the report…"):
            data = build_excel_report(P, RES, stress_tables(FINGERPRINT) if (inc_stress and not RES["problems"]) else None,
                                      mc_now["res"] if mc_ok else None)
        st.session_state.report = dict(fp=FINGERPRINT, data=data, when=date.today().strftime("%d %b %Y"))
    rep = st.session_state.get("report")
    if rep and rep["fp"] == FINGERPRINT:
        st.download_button("⬇️ Download Excel report", rep["data"], type="primary", width="stretch",
                           file_name=f"{P.info.name.split(' (')[0].replace(' ', '_')}_Feasibility_Report.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    elif rep:
        st.caption("Inputs changed since the last report – build it again.")
    st.divider()
    st.download_button("💾 Save project file", json.dumps(to_dict(P), indent=2, ensure_ascii=False),
                       file_name=f"{P.info.name.split(' (')[0].replace(' ', '_')}.json", mime="application/json",
                       width="stretch")
    up = st.file_uploader("📂 Open project file or Excel report", type=["json", "xlsx"])
    if up is not None and st.session_state.get("loaded_file") != up.file_id:
        try:
            raw = up.getvalue()
            st.session_state.project = project_from_excel(raw) if up.name.lower().endswith(".xlsx") else from_dict(json.loads(raw))
            st.session_state.loaded_file = up.file_id
            st.rerun()
        except Exception as exc:
            st.error(f"Could not open this file: {exc}")
    if st.button("↺ Reset to sample project", width="stretch"):
        st.session_state.project = sample_project()
        st.rerun()

# ============================================================================ page 0: dashboard
if page.startswith("0"):
    if RES:
        render_dashboard(P, RES)
    else:
        st.error("The dashboard cannot be drawn until the errors on the other pages are fixed (see '9 · Checks & summary').")

# ============================================================================ stress testing & Monte Carlo
elif page.startswith("S"):
    if RES and not RES["problems"]:
        render_stress(P, FINGERPRINT, stress_tables)
    else:
        st.error("Stress tests need a model without errors – fix the issues listed on '9 · Checks & summary' first.")

# ============================================================================ page 1: project & land
elif page.startswith("1"):
    st.header("1 · Project & land")
    st.caption("Fields with ⚠️ underneath need fixing. All amounts in ₹; land in sq yd.")
    a, b = st.columns(2)
    with a:
        st.subheader("Project")
        P.info.name = st.text_input("Project name", P.info.name)
        P.info.location = st.text_input("Location", P.info.location)
        P.info.project_type = st.selectbox("Project type", PROJECT_TYPES, PROJECT_TYPES.index(P.info.project_type),
                                           help="Only products whose zone belongs to this type are calculated (Mixed = all).")
        P.info.start_date = st.date_input("Project start = Q1 (quarter-end date)", P.info.start_date,
                                          min_value=date(2020, 1, 1), max_value=date(2045, 12, 31), format="DD/MM/YYYY")
        show("Project", "start_date")
        P.info.deal_type = st.radio("Deal type", DEAL_TYPES, DEAL_TYPES.index(P.info.deal_type), horizontal=True)
        P.info.entity = st.radio("Taxable entity", ENTITIES, ENTITIES.index(P.info.entity), horizontal=True)
        names = [s.name for s in P.scenarios]
        P.info.scenario = st.selectbox("Active scenario", names, names.index(P.info.scenario) if P.info.scenario in names else 0)
        show("Project", "scenario")
        ov = st.number_input("Lifecycle for ROCE / CAGR (years) – 0 = use project span", value=float(P.info.lifecycle_override_years or 0),
                             min_value=0.0, step=0.5)
        P.info.lifecycle_override_years = ov or None
    with b:
        st.subheader("Land")
        L = P.land
        L.area_sqyd = st.number_input("Land area (sq yd)", value=float(L.area_sqyd), min_value=0.0, step=100.0)
        st.caption(f"= {L.area_sqyd * SQFT_PER_SQYD:,.0f} sq ft · {L.area_sqyd / SQYD_PER_ACRE:,.2f} acres · "
                   f"{L.area_sqyd / SQYD_PER_BIGHA:,.2f} bigha")
        L.market_rate = st.number_input("Current market rate (₹ / sq yd)", value=float(L.market_rate), min_value=0.0, step=500.0)
        L.dlc_rate_sqm = st.number_input("DLC / circle rate (₹ / sq m)", value=float(L.dlc_rate_sqm), min_value=0.0, step=100.0)
        show("Land", "land_rates")
        if P.info.deal_type == "JV":
            L.lo_share = pct_in("Landowner revenue share (%)", L.lo_share)
            show("Land", "lo_share")
            L.stamp_duty_jv = pct_in("Stamp duty + registration on JV (% of DLC value)", L.stamp_duty_jv, step=0.05)
            if RES:
                cr = RES["costs"]
                lo_px = cr.land_cost * CRORE / L.area_sqyd if L.area_sqyd else 0
                st.info(f"Landowner effectively gets ₹{lo_px:,.0f} / sq yd = "
                        f"{lo_px / L.market_rate - 1:+.1%} vs today's market rate.", icon="💡")
        else:
            L.purchase_rate = st.number_input("Purchase rate (₹ / sq yd)", value=float(L.purchase_rate), min_value=0.0, step=500.0)
            show("Land", "purchase_rate")
            L.stamp_duty_outright = pct_in("Stamp duty + registration – outright (%)", L.stamp_duty_outright, step=0.05)
            c1, c2, c3 = st.columns(3)
            L.payment_curve = c1.selectbox("Land payment curve", LAND_CURVES, LAND_CURVES.index(L.payment_curve))
            L.payment_start_q = int(c2.number_input("Start quarter", value=int(L.payment_start_q), min_value=1, max_value=HORIZON_Q))
            L.payment_end_q = int(c3.number_input("End quarter", value=int(L.payment_end_q), min_value=1, max_value=HORIZON_Q,
                                                  disabled=L.payment_curve == "Upfront"))
            show("Land", "payment")

# ============================================================================ page 2: scenarios & zones
elif page.startswith("2"):
    st.header("2 · Scenarios & development zones")
    st.subheader("Scenarios")
    st.caption("Sales period multiplier 1.5 = products take 50% longer to sell. Delay pushes every fixed launch / construction start later.")
    df = pd.DataFrame([{"Scenario": s.name, "Sales period ×": s.sales_period_mult, "Price change %": s.price_change * 100,
                        "Construction cost change %": s.cost_change * 100, "Delay (quarters)": s.delay_q,
                        "Check": row_status("Scenarios", s.name)} for s in P.scenarios])
    ed = st.data_editor(df, key="ed_scen", hide_index=True, width="stretch", num_rows="dynamic",
                        column_config={"Sales period ×": st.column_config.NumberColumn(min_value=0.1, step=0.05, format="%.2f"),
                                       "Delay (quarters)": st.column_config.NumberColumn(min_value=0, step=1),
                                       "Check": st.column_config.TextColumn(disabled=True)})
    if not ed.equals(df):
        P.scenarios = [Scenario(str(r["Scenario"] or f"Scenario {i+1}"), float(r["Sales period ×"] or 1), float(r["Price change %"] or 0) / 100,
                                float(r["Construction cost change %"] or 0) / 100, int(r["Delay (quarters)"] or 0))
                       for i, r in ed.iterrows()]
        rerun_after_edit("ed_scen")
    show("Scenarios", "names")

    st.subheader("Development zones")
    used = {"Villa": ["Villa Development"], "Apartments": ["Apartment Development"], "Plotted": ["Plotted Development"]}.get(P.info.project_type, ZONES)
    df = pd.DataFrame([{"Zone": z.name, "Share of land %": z.share * 100,
                        "Land area (sq ft)": round(z.share * P.land.area_sqyd * SQFT_PER_SQYD),
                        "In this project type?": "Yes" if (z.name in used or z.name == "Other / Clubhouse") else "No"} for z in P.zones])
    ed = st.data_editor(df, key="ed_zone", hide_index=True, width="stretch", num_rows="fixed",
                        column_config={"Zone": st.column_config.TextColumn(disabled=True),
                                       "Land area (sq ft)": st.column_config.NumberColumn(disabled=True, format="%d"),
                                       "In this project type?": st.column_config.TextColumn(disabled=True)})
    if not ed.equals(df):
        for z, (_, r) in zip(P.zones, ed.iterrows()):
            z.share = float(r["Share of land %"] or 0) / 100
        rerun_after_edit("ed_zone")
    st.caption(f"Total share: {sum(z.share for z in P.zones):.1%}")
    show("Zones", "zones")

# ============================================================================ page 3: products
elif page.startswith("3"):
    st.header("3 · Product mix")
    st.caption("One row per product. Add a row with the ➕ at the bottom of the table; tick **Include** to use it. "
               "**Active** is automatic: included AND its zone fits the project type.")
    active = {p.name for p in P.active_products()}
    plans = [pl.name for pl in P.plans]
    rev = RES["curves"].revenue if RES else {}
    df = pd.DataFrame([{
        "Include": p.include, "Product": p.name, "Zone": p.zone, "Category": p.category,
        "Area (sq ft)": p.area_sqft, "Sales rate (₹/sq ft)": p.rate, "Construction (₹/sq ft)": p.construction_rate,
        "Launch Q (fixed)": p.launch_q, "Sales period (qtrs)": p.sales_period_q, "Sales curve": p.sales_curve,
        "Payment plan": p.clp_plan, "Construction start Q (fixed)": p.construction_start_q,
        "Construction (qtrs)": p.construction_duration_q, "Construction curve": p.construction_curve,
        "Active": "Yes" if p.name in active else ("Excluded by type" if p.include else "Off"),
        "Revenue (₹ Cr)": round(rev.get(p.name, 0.0), 2), "Check": row_status("Products", p.name)} for p in P.products])
    num = lambda **k: st.column_config.NumberColumn(**k)
    ed = st.data_editor(df, key="ed_prod", hide_index=True, width="stretch", num_rows="dynamic", column_config={
        "Include": st.column_config.CheckboxColumn(default=True),
        "Zone": st.column_config.SelectboxColumn(options=ZONES, required=True, default="Apartment Development"),
        "Category": st.column_config.SelectboxColumn(options=CATEGORIES, required=True, default="Apartment"),
        "Area (sq ft)": num(min_value=0, step=1000, format="%d"), "Sales rate (₹/sq ft)": num(min_value=0, step=100, format="%d"),
        "Construction (₹/sq ft)": num(min_value=0, step=50, format="%d"),
        "Launch Q (fixed)": num(min_value=1, max_value=HORIZON_Q, step=1), "Sales period (qtrs)": num(min_value=1, max_value=HORIZON_Q, step=1),
        "Sales curve": st.column_config.SelectboxColumn(options=BASIC_CURVES, required=True, default="Even"),
        "Payment plan": st.column_config.SelectboxColumn(options=plans, required=True, default=plans[0] if plans else None),
        "Construction start Q (fixed)": num(min_value=1, max_value=HORIZON_Q, step=1),
        "Construction (qtrs)": num(min_value=1, max_value=HORIZON_Q, step=1),
        "Construction curve": st.column_config.SelectboxColumn(options=BASIC_CURVES, required=True, default="S-curve"),
        "Active": st.column_config.TextColumn(disabled=True), "Revenue (₹ Cr)": num(disabled=True, format="%.2f"),
        "Check": st.column_config.TextColumn(disabled=True, width="large")})
    if not ed.equals(df):
        old = {i: p for i, p in enumerate(P.products)}
        new = []
        for i, r in ed.reset_index(drop=True).iterrows():
            v = lambda col, d: d if pd.isna(r[col]) else r[col]
            prev = old.get(i)
            name = str(v("Product", f"New product {i+1}"))
            prod = Product(name, v("Zone", "Apartment Development"), v("Category", "Apartment"), bool(v("Include", True)),
                           float(v("Area (sq ft)", 0)), float(v("Sales rate (₹/sq ft)", 0)), float(v("Construction (₹/sq ft)", 0)),
                           int(v("Launch Q (fixed)", 1)), int(v("Sales period (qtrs)", 1)), v("Sales curve", "Even"),
                           v("Payment plan", plans[0] if plans else ""), int(v("Construction start Q (fixed)", 1)),
                           int(v("Construction (qtrs)", 1)), v("Construction curve", "S-curve"),
                           copy.deepcopy(prev.timing) if prev else Timing())
            if prev and prev.name != name:                       # renamed -> keep links pointing to it
                for q in P.products:
                    for attr in ("launch_link_product", "cons_link_product"):
                        if getattr(q.timing, attr) == prev.name: setattr(q.timing, attr, name)
                for q in new:
                    for attr in ("launch_link_product", "cons_link_product"):
                        if getattr(q.timing, attr) == prev.name: setattr(q.timing, attr, name)
            new.append(prod)
        P.products = new
        rerun_after_edit("ed_prod")
    show("Products", "names"); show("Products", "active")
    if RES:
        st.caption(f"Active saleable area {RES['costs'].total_sa:,.0f} sq ft · GDV ₹{RES['costs'].total_revenue:,.2f} Cr · "
                   f"construction ₹{RES['costs'].total_construction:,.2f} Cr")

# ============================================================================ page 4: product timing
elif page.startswith("4"):
    st.header("4 · Product timing – how each launch and construction start is decided")
    st.caption("Fixed = uses the quarter typed on page 3. Linked = X quarters after an event of a product listed ABOVE it "
               "(put the lead product first). Offset 0 = same quarter, 1 = next quarter, −1 = one before.")
    names = [p.name for p in P.products]
    notes = {n: t.note for n, t in RES["timeline"].products.items()} if RES else {}
    df = pd.DataFrame([{
        "Product": p.name, "Launch timing": p.timing.launch_mode, "Launch – linked product": p.timing.launch_link_product,
        "Launch – event": p.timing.launch_link_event, "Launch offset": p.timing.launch_offset,
        "Construction timing": p.timing.cons_mode, "Construction – linked product": p.timing.cons_link_product,
        "Construction – event": p.timing.cons_link_event, "Construction offset": p.timing.cons_offset,
        "Result": notes.get(p.name, "— (not active)"), "Check": row_status("Timing", p.name)} for p in P.products])
    sel = lambda opts: st.column_config.SelectboxColumn(options=opts)
    ed = st.data_editor(df, key="ed_time", hide_index=True, width="stretch", num_rows="fixed", column_config={
        "Product": st.column_config.TextColumn(disabled=True), "Launch timing": sel(LAUNCH_MODES),
        "Launch – linked product": sel(names), "Launch – event": sel(LINK_EVENTS),
        "Launch offset": st.column_config.NumberColumn(min_value=-8, max_value=40, step=1),
        "Construction timing": sel(CONS_MODES), "Construction – linked product": sel(names), "Construction – event": sel(LINK_EVENTS),
        "Construction offset": st.column_config.NumberColumn(min_value=-8, max_value=40, step=1),
        "Result": st.column_config.TextColumn(disabled=True, width="large"), "Check": st.column_config.TextColumn(disabled=True)})
    if not ed.equals(df):
        for p, (_, r) in zip(P.products, ed.iterrows()):
            n = lambda col, d=None: d if pd.isna(r[col]) else r[col]
            p.timing = Timing(n("Launch timing", "Fixed quarter"), n("Launch – linked product"), n("Launch – event"), int(n("Launch offset", 0)),
                              n("Construction timing", "Fixed quarter"), n("Construction – linked product"), n("Construction – event"),
                              int(n("Construction offset", 0)))
        rerun_after_edit("ed_time")
    if RES:
        for e in RES["timeline"].errors: st.error(e, icon="⚠️")
        tl = RES["timeline"]
        st.subheader("Timeline (S = selling · C = construction · # = both)")
        rows = []
        for t in tl.products.values():
            rows.append({"Product": t.name, **{f"Q{q}": ("#" if (t.launch <= q <= t.sales_end and t.cons_start <= q <= t.cons_end)
                                                      else "S" if t.launch <= q <= t.sales_end else "C" if t.cons_start <= q <= t.cons_end else "")
                                               for q in range(1, max(tl.last_q, 1) + 1)}})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

# ============================================================================ page 5: cost heads
elif page.startswith("5"):
    st.header("5 · Cost heads")
    st.caption("Change rates, switch heads on/off and pick how each cost is spread over time. Grey 'Auto' rows are calculated "
               "elsewhere (land page, product table, calculators). Percent inputs are typed as % (4 = 4%).")
    META = {  # key: (how it is calculated, unit of input 1, unit of input 2)
        "land": ("JV: landowner share × revenue | Outright: price × area", "Auto", ""), "sd": ("From land page", "Auto", ""),
        "brok": ("% × land value", "%", ""), "ovh": ("% × total revenue", "%", ""),
        "mkt": ("Input 1 % × built-up revenue + Input 2 % × plotted revenue", "%", "%"),
        "legal": ("₹/sq ft × total saleable area", "₹/sq ft", ""), "ews": ("Loss ₹/sq ft × EWS share × saleable area", "₹/sq ft", "%"),
        "cont": ("% × base chosen in 'Basis'", "%", ""), "edc": ("Input 1 per 'Basis'", "per basis", ""),
        "hotel": ("Fee per key (₹) × number of keys", "₹/key", "keys"), "furn": ("₹/sq ft × studio area", "₹/sq ft", ""),
        "gst": ("(Commercial + plot revenue) × unsold % × GST % × developer share", "% GST", "% unsold"),
        "aif": ("Calculator page 6", "Auto", ""), "bar": ("Calculator page 6", "Auto", "")}
    for k, n, cat in CONSTRUCTION_HEADS: META[k] = (f"Σ {cat} products (page 3)", "Auto", "")
    PCT1 = {"brok", "ovh", "mkt", "cont", "gst"}; PCT2 = {"mkt", "ews", "gst"}
    amounts = RES["costs"].amounts if RES else {}
    tsa = RES["costs"].total_sa if RES else 0
    def shown1(c):
        if c.rate1 is None: return None
        is_pct = c.key in PCT1 or (c.key == "edc" and c.rate2 == "% of construction cost") or \
                 (c.key.startswith("spare") and c.basis in ("% of total revenue", "% of construction cost"))
        return c.rate1 * 100 if is_pct else c.rate1
    df = pd.DataFrame([{
        "Cost head": c.name, "How it is calculated": META.get(c.key, ("Spare: per 'Basis'", "per basis", ""))[0],
        "Input 1": shown1(c), "Unit 1": META.get(c.key, ("", "per basis", ""))[1],
        "Input 2": (c.rate2 * 100 if c.key in PCT2 else c.rate2) if isinstance(c.rate2, (int, float)) else None,
        "Unit 2": META.get(c.key, ("", "", ""))[2],
        "Basis": c.rate2 if c.key in ("cont", "edc") else (c.basis if c.key.startswith("spare") else None),
        "Applicable": c.applicable,
        "Phasing curve": ("Follow Collections" if P.info.deal_type == "JV" else P.land.payment_curve) if c.key == "land" else c.curve,
        "Start Q": c.start_q, "End Q": c.end_q,
        "Amount (₹ Cr)": round(amounts.get(c.key, 0.0), 2),
        "₹ / sq ft": round(amounts.get(c.key, 0.0) * CRORE / tsa, 0) if tsa else 0.0,
        "Check": row_status("Costs", c.key)} for c in P.costs])
    ed = st.data_editor(df, key="ed_cost", hide_index=True, width="stretch", num_rows="fixed", column_config={
        "Cost head": st.column_config.TextColumn(width="medium"), "How it is calculated": st.column_config.TextColumn(disabled=True),
        "Unit 1": st.column_config.TextColumn(disabled=True), "Unit 2": st.column_config.TextColumn(disabled=True),
        "Basis": st.column_config.SelectboxColumn(options=sorted(set(SPARE_BASES + EDC_BASES + CONTINGENCY_BASES))),
        "Phasing curve": st.column_config.SelectboxColumn(options=COST_CURVES),
        "Start Q": st.column_config.NumberColumn(min_value=1, max_value=HORIZON_Q, step=1),
        "End Q": st.column_config.NumberColumn(min_value=1, max_value=HORIZON_Q, step=1),
        "Amount (₹ Cr)": st.column_config.NumberColumn(disabled=True, format="%.2f"),
        "₹ / sq ft": st.column_config.NumberColumn(disabled=True, format="%d"),
        "Check": st.column_config.TextColumn(disabled=True, width="large")})
    if not ed.equals(df):
        auto = {"land", "sd", "aif", "bar"} | {k for k, _, _ in CONSTRUCTION_HEADS}
        for c, (_, r) in zip(P.costs, ed.iterrows()):
            g = lambda col: None if pd.isna(r[col]) else r[col]
            if c.key.startswith("spare"): c.name = str(g("Cost head") or c.name); c.basis = g("Basis")
            c.applicable = bool(r["Applicable"])
            if c.key != "land":
                c.curve = g("Phasing curve") or c.curve
                c.start_q = None if g("Start Q") is None else int(g("Start Q"))
                c.end_q = None if g("End Q") is None else int(g("End Q"))
            if c.key in auto: continue
            v1 = g("Input 1")
            if v1 is not None:
                is_pct = c.key in PCT1 or (c.key == "edc" and (g("Basis") or c.rate2) == "% of construction cost") or \
                         (c.key.startswith("spare") and c.basis in ("% of total revenue", "% of construction cost"))
                c.rate1 = float(v1) / 100 if is_pct else float(v1)
            if c.key in ("cont", "edc"):
                c.rate2 = g("Basis") or c.rate2
            elif c.key in PCT2 or c.key == "hotel":
                v2 = g("Input 2")
                c.rate2 = (float(v2) / 100 if c.key in PCT2 else float(v2)) if v2 is not None else c.rate2
        rerun_after_edit("ed_cost")
    if st.button("➕ Add a spare cost head"):
        n = sum(1 for c in P.costs if c.key.startswith("spare")) + 1
        P.costs.append(CostHead(f"spare{n}", f"Other cost {n}", rate1=0.0, applicable=True, curve="Follow Construction",
                                basis="Lump sum (Rs Cr)"))
        rerun_after_edit("ed_cost")
    if RES:
        st.metric("TOTAL COST", f"₹{RES['costs'].total_cost:,.2f} Cr", f"{RES['costs'].total_cost / RES['costs'].total_revenue:.1%} of GDV",
                  delta_color="off")

# ============================================================================ page 6: calculators
elif page.startswith("6"):
    st.header("6 · Calculators")
    t1, t2, t3 = st.tabs(["BAR / premium FAR", "AIF cost", "Initial investment"])
    with t1:
        b = P.bar
        c1, c2 = st.columns(2)
        b.authority = c1.selectbox("Authority", BAR_AUTHORITIES, BAR_AUTHORITIES.index(b.authority))
        b.land_use = c2.selectbox("Land use", BAR_LAND_USES, BAR_LAND_USES.index(b.land_use))
        b.free_far = c1.number_input("Free FAR (× land area)", value=float(b.free_far), min_value=0.0, step=0.1)
        b.loading_factor = c2.number_input("Loading factor (saleable ÷ built-up)", value=float(b.loading_factor), min_value=0.01, step=0.05)
        b.reserved_price_sqm = c1.number_input("Reserved price (₹ / sq m)", value=float(b.reserved_price_sqm), min_value=0.0, step=100.0)
        b.gst_applicable = c2.checkbox("GST on BAR applicable", b.gst_applicable)
        b.gst_rate = pct_in("GST rate on BAR (%)", b.gst_rate)
        st.write("**BAR reserved-price % table** (blank = combination not allowed)")
        df = pd.DataFrame({a: {u: (None if b.pct_table[u].get(a) is None else b.pct_table[u][a] * 100) for u in BAR_LAND_USES}
                           for a in BAR_AUTHORITIES})
        ed = st.data_editor(df, key="ed_bar")
        if not ed.equals(df):
            b.pct_table = {u: {a: (None if pd.isna(ed.loc[u, a]) else float(ed.loc[u, a]) / 100) for a in BAR_AUTHORITIES} for u in BAR_LAND_USES}
            rerun_after_edit("ed_bar")
        show("BAR", "bar")
        if RES:
            x = RES["costs"].bar
            st.success(f"Free {x['free_sqm']:,.0f} sq m · planned {x['planned_sqm']:,.0f} sq m · extra {x['extra_sqm']:,.0f} sq m × "
                       f"₹{b.reserved_price_sqm:,.0f} × {x['pct']:.0%} = **₹{x['cost']:.2f} Cr**")
    with t2:
        a = P.aif
        a.rate = pct_in("Interest rate (% p.a.)", a.rate)
        a.tenure_years = st.number_input("Tenure (years)", value=float(a.tenure_years), min_value=0.0, step=0.5)
        a.compounding = st.selectbox("Compounding", list(COMPOUNDING), list(COMPOUNDING).index(a.compounding))
        show("AIF", "aif")
        if RES:
            x = RES["costs"].aif
            st.info(f"Principal (land + stamp duty + brokerage) ₹{x['principal']:,.2f} Cr → interest **₹{x['cost']:,.2f} Cr**. "
                    f"Switch the 'AIF Cost' head on (page 5) to include it.", icon="💡")
    with t3:
        ii = P.initial
        st.write("**JV – advance to landowner and early payments** (only used in JV deals)")
        c1, c2, c3 = st.columns(3)
        ii.advance_pct = pct_in("Advance to landowner (% of land value at market)", ii.advance_pct)
        ii.dd_amount = c1.number_input("Paid on due diligence (₹ Cr)", value=float(ii.dd_amount), min_value=0.0, step=0.5)
        ii.da_amount = c2.number_input("Paid at DA (₹ Cr)", value=float(ii.da_amount), min_value=0.0, step=0.5)
        show("Initial investment", "dd_da")
        ii.legal_share = pct_in("Share of legal & compliance paid before DA (%)", ii.legal_share)
        ii.bar_share = pct_in("Share of BAR paid upfront (%)", ii.bar_share)
        ii.dev_cost_pre_da = c3.number_input("Development cost before DA (₹ Cr)", value=float(ii.dev_cost_pre_da), min_value=0.0, step=0.5)
        ii.marketing_pre_launch = c3.number_input("Pre-launch marketing (₹ Cr)", value=float(ii.marketing_pre_launch), min_value=0.0, step=0.5)
        labels = {"token": "Term-sheet token (balance)", "dd": "Due diligence", "da": "At DA", "legal": "Legal & compliance",
                  "dev": "Pre-DA development", "marketing": "Pre-launch marketing", "sd": "Stamp duty", "brok": "Brokerage", "bar": "BAR (upfront share)"}
        items = RES["costs"].initial_items if RES else {}
        df = pd.DataFrame([{"Item": labels[k], "Amount (₹ Cr)": round(items.get(k, 0.0), 2), "Payout quarter": q}
                           for k, q in ii.payout_q.items()])
        ed = st.data_editor(df, key="ed_ii", hide_index=True, num_rows="fixed", column_config={
            "Item": st.column_config.TextColumn(disabled=True), "Amount (₹ Cr)": st.column_config.NumberColumn(disabled=True, format="%.2f"),
            "Payout quarter": st.column_config.NumberColumn(min_value=1, max_value=HORIZON_Q, step=1)})
        if not ed.equals(df):
            for k, (_, r) in zip(list(ii.payout_q), ed.iterrows()):
                ii.payout_q[k] = int(r["Payout quarter"]) if not pd.isna(r["Payout quarter"]) else ii.payout_q[k]
            rerun_after_edit("ed_ii")
        show("Initial investment", "payout_q")
        st.write("**Outright – initial outlay** = land + stamp duty + brokerage + shares below")
        ii.outright_construction_share = pct_in("Share of built-up construction (%)", ii.outright_construction_share)
        ii.outright_legal_share = pct_in("Share of legal & compliance (%)", ii.outright_legal_share)
        if RES:
            cr = RES["costs"]
            st.success(f"Initial investment – JV ₹{cr.initial_jv:,.2f} Cr · Outright ₹{cr.initial_outright:,.2f} Cr · "
                       f"**used ({P.info.deal_type}) ₹{cr.initial_used:,.2f} Cr**")

# ============================================================================ page 7: payment plans
elif page.startswith("7"):
    st.header("7 · Payment plans (CLP)")
    st.caption("Booking-linked: value = quarters after booking (0–12). Construction-linked: value = % of that product's construction "
               "(e.g. 35). Each plan must total exactly 100%. Add as many milestones as you need with ➕.")
    P.catch_up_lag = int(st.number_input("Catch-up lag – late buyers pay milestones already reached this many quarters after booking",
                                         value=int(P.catch_up_lag), min_value=0, max_value=4, step=1))
    show("CLP", "catch_up_lag")
    names = [pl.name for pl in P.plans]
    used_by = {pl: [p.name for p in P.products if p.clp_plan == pl] for pl in names}
    c1, c2 = st.columns([2, 1])
    choice = c1.selectbox("Plan", names, format_func=lambda n: f"{n}  {'⚠️' if issues_for('CLP', n) else '✔'}  "
                                                              f"(used by: {', '.join(used_by[n]) or 'none'})")
    plan = P.plan(choice)
    new_name = c2.text_input("Rename plan", plan.name)
    if new_name and new_name != plan.name and new_name not in names:
        for p in P.products:
            if p.clp_plan == plan.name: p.clp_plan = new_name
        plan.name = new_name
        st.rerun()
    df = pd.DataFrame([{"Milestone": m.name, "Trigger": m.trigger,
                        "Value": m.value if m.trigger == "Booking + quarters" else round(m.value * 100, 4),
                        "% of sale": round(m.pct * 100, 4)} for m in plan.milestones])
    if df.empty:
        df = pd.DataFrame(columns=["Milestone", "Trigger", "Value", "% of sale"])
    ed = st.data_editor(df, key=f"ed_plan_{choice}", hide_index=True, width="stretch", num_rows="dynamic", column_config={
        "Trigger": st.column_config.SelectboxColumn(options=TRIGGERS, required=True, default="Construction % complete"),
        "Value": st.column_config.NumberColumn(min_value=0, max_value=100, help="quarters (booking) or % (construction)"),
        "% of sale": st.column_config.NumberColumn(min_value=0, max_value=100, step=0.5, format="%.2f")})
    if not ed.equals(df):
        ms = []
        for _, r in ed.iterrows():
            if pd.isna(r["Milestone"]) and pd.isna(r["% of sale"]): continue
            trig = r["Trigger"] if not pd.isna(r["Trigger"]) else "Construction % complete"
            val = 0.0 if pd.isna(r["Value"]) else float(r["Value"])
            ms.append(Milestone(str(r["Milestone"]) if not pd.isna(r["Milestone"]) else "Milestone", trig,
                                val if trig == "Booking + quarters" else val / 100, 0.0 if pd.isna(r["% of sale"]) else float(r["% of sale"]) / 100))
        plan.milestones = ms
        rerun_after_edit(f"ed_plan_{choice}")
    total = sum(m.pct for m in plan.milestones)
    (st.success if abs(total - 1) < 1e-6 else st.error)(f"Plan total: {total:.2%}" + ("" if abs(total - 1) < 1e-6 else " – must be exactly 100%"))
    for i in issues_for("CLP", plan.name):
        if "totals" not in i.message: st.error(i.message, icon="⚠️")
    if RES:
        sched = [s for s in RES["collections"].schedule if s.plan == plan.name and s.due_q]
        if sched:
            st.write("**When construction-linked milestones fall due** (for products using this plan)")
            st.dataframe(pd.DataFrame([{"Product": s.product, "Milestone": s.name, "Falls due": s.text} for s in sched]),
                         hide_index=True, width="stretch")
    st.divider()
    c1, c2, c3 = st.columns(3)
    nn = c1.text_input("New plan name", placeholder="e.g. CLP – 12-Floor Tower")
    if c1.button("➕ Create empty plan") and nn and nn not in names:
        P.plans.append(ClpPlan(nn, [])); st.rerun()
    if c2.button("⧉ Duplicate this plan"):
        k = 2
        while f"{plan.name} ({k})" in names: k += 1
        P.plans.append(ClpPlan(f"{plan.name} ({k})", copy.deepcopy(plan.milestones))); st.rerun()
    if c3.button("🗑 Delete this plan", disabled=bool(used_by[plan.name]),
                 help="Only plans not used by any product can be deleted."):
        P.plans = [pl for pl in P.plans if pl.name != plan.name]; st.rerun()
    show("CLP", "plan_names")

# ============================================================================ page 8: tax & benchmarks
elif page.startswith("8"):
    st.header("8 · Tax, cost of equity & KPI benchmarks")
    f = P.finance
    c1, c2, c3 = st.columns(3)
    with c1:
        f.tax_company = pct_in("Tax rate – Company (%)", f.tax_company, help="Verify with Finance (statutory 115BAA ≈ 25.17%)")
        f.tax_llp = pct_in("Tax rate – LLP (%)", f.tax_llp, help="Verify with Finance (statutory ≈ 34.94%)")
        f.cost_of_equity = pct_in("Cost of equity / discount rate (%)", f.cost_of_equity)
        show("Finance", "finance")
    labels = {"project_irr": "Project IRR (%)", "developer_irr": "Developer IRR (%)", "roce": "ROCE (%)", "cagr": "CAGR (%)",
              "pat_margin": "PAT margin (%)", "ebitda_margin": "EBITDA margin (%)"}
    with c2:
        st.write("**Benchmarks** (green when beaten)")
        for k in ["project_irr", "developer_irr", "roce"]: f.benchmarks[k] = pct_in(labels[k], f.benchmarks[k], key=f"bm_{k}")
    with c3:
        st.write("&nbsp;")
        for k in ["cagr", "pat_margin", "ebitda_margin"]: f.benchmarks[k] = pct_in(labels[k], f.benchmarks[k], key=f"bm_{k}")
        f.benchmarks["equity_multiple"] = st.number_input("Equity multiple (x)", value=float(f.benchmarks["equity_multiple"]), min_value=0.0, step=0.1)

# ============================================================================ page 9: checks & summary
else:
    st.header("9 · Checks & summary")
    if not issues and RES and not RES["problems"]:
        st.success("✔ ALL CHECKS PASSED – the results below can be used.")
    else:
        for page_name, secs in PAGE_SECTIONS.items():
            mine = [i for i in issues if i.section in secs]
            if mine:
                st.subheader(page_name)
                for i in mine: st.error(i.message, icon="⚠️")
        if RES:
            for p in RES["problems"]:
                if not any(p.endswith(i.message) for i in issues): st.error(p, icon="⚠️")
        if ENGINE_ERROR:
            st.error(f"The engine could not run with these inputs: {ENGINE_ERROR}")
        if RES is None:
            st.info("Results appear once the product, timing and payment-plan errors above are fixed.")
    if RES:
        pnl, m = RES["cashflow"].pnl, RES["cashflow"].metrics
        st.subheader("Headline results")
        c = st.columns(4)
        c[0].metric("GDV", f"₹{pnl['revenue']:,.1f} Cr"); c[1].metric("Total cost", f"₹{pnl['total_cost']:,.1f} Cr")
        c[2].metric("EBITDA", f"₹{pnl['ebitda']:,.1f} Cr", f"{pnl['ebitda_margin']:.1%} margin", delta_color="off")
        c[3].metric("PAT", f"₹{pnl['pat']:,.1f} Cr", f"{pnl['pat_margin']:.1%} margin", delta_color="off")
        c = st.columns(4)
        fmt = lambda v: "n/a" if v is None else f"{v:.1%}"
        c[0].metric("Developer IRR", fmt(m["developer_irr"])); c[1].metric("Developer NPV", f"₹{m['developer_npv']:,.1f} Cr")
        c[2].metric("Peak investment", f"₹{m['peak_investment']:,.1f} Cr", f"in Q{m['peak_quarter']}" if m["peak_quarter"] else "", delta_color="off")
        c[3].metric("Payback", f"Q{m['payback_q']}" if m["payback_q"] else "never",
                    m["payback_date"].strftime("%b %Y") if m["payback_date"] else "", delta_color="off")
        st.caption("Charts, KPI cards and takeaways are on '0 · Dashboard'.")

# ============================================================================ keep results in step with the inputs
# Fields above change the project while this page is drawn; if anything changed, redraw once so every
# number, check and error message reflects the new inputs.
if json.dumps(to_dict(P), sort_keys=True, default=str) != FINGERPRINT:
    st.rerun()
