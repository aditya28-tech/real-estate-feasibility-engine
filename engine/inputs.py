"""
engine/inputs.py  -  STEP 1: the input structure of the Real Estate Feasibility Engine.

Everything a user types on the Excel INPUTS sheet is described here as Python "dataclasses"
(simple containers with named fields). The rest of the app (timeline, curves, collections,
cash flow, metrics) will only ever read from a `Project` object built from these classes.

Units used everywhere:  areas in sq ft (land in sq yd), rates in Rs, amounts in Rs Crore,
timing as QUARTER NUMBERS counted from the project start (Q1 = start quarter).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Optional

# --------------------------------------------------------------------------------------------
# 1. CONSTANTS AND ALLOWED VALUES (the Excel "LISTS" sheet)
# --------------------------------------------------------------------------------------------
CRORE = 10_000_000          # 1 Crore = 1,00,00,000
HORIZON_Q = 40              # model length: 40 quarters = 10 years
MAX_BOOKING_LAG = 12        # booking-linked milestones: 0..12 quarters after booking

SQFT_PER_SQYD = 9.0
SQM_PER_SQYD = 0.83612736
SQYD_PER_ACRE = 4840.0
SQYD_PER_BIGHA = 3025.0     # Rajasthan pucca bigha - change for other states

DEAL_TYPES = ["JV", "Outright"]
ENTITIES = ["Company", "LLP"]
PROJECT_TYPES = ["Villa", "Plotted", "Apartments", "Mixed Development"]
ZONES = ["Villa Development", "Apartment Development", "Plotted Development", "Other / Clubhouse"]
CATEGORIES = ["Villa", "Apartment", "Studio", "Plot", "Commercial", "Institutional", "EWS/LIG"]
BASIC_CURVES = ["Even", "Front-loaded", "Back-loaded", "S-curve"]
LAND_CURVES = ["Upfront"] + BASIC_CURVES
COST_CURVES = LAND_CURVES + ["Follow Construction", "Follow Sales", "Follow Collections",
                             "Follow Project Life", "At Project End"]
MANUAL_CURVES = LAND_CURVES                      # curves that need start / end quarters
SPARE_BASES = ["Rs/sq ft (total saleable area)", "% of total revenue", "% of construction cost",
               "Lump sum (Rs Cr)", "Rs/sq yd (land area)"]
EDC_BASES = ["Rs/sq ft (total saleable area)", "% of construction cost", "Lump sum (Rs Cr)"]
CONTINGENCY_BASES = ["Construction cost", "All costs excl. land heads"]
TRIGGERS = ["Booking + quarters", "Construction % complete"]
LAUNCH_MODES = ["Fixed quarter", "Linked to another product", "After own construction start"]
CONS_MODES = ["Fixed quarter", "After own launch", "Linked to another product"]
LINK_EVENTS = ["Launch", "Sales end", "Construction start", "Construction 50%", "Construction end"]
BAR_AUTHORITIES = ["RIICO", "JDA"]
BAR_LAND_USES = ["Industrial", "Residential", "Commercial"]
COMPOUNDING = {"Annually": 1, "Half-yearly": 2, "Quarterly": 4, "Monthly": 12}

# Project type -> development zones that are calculated (Mixed = all zones)
ZONES_FOR_TYPE = {
    "Villa": ["Villa Development", "Other / Clubhouse"],
    "Apartments": ["Apartment Development", "Other / Clubhouse"],
    "Plotted": ["Plotted Development", "Other / Clubhouse"],
    "Mixed Development": ZONES,
}

# Construction cost heads: one per product category (key, display name, category)
CONSTRUCTION_HEADS = [
    ("villa", "Villa Construction Cost", "Villa"),
    ("apt", "APT Construction Cost", "Apartment"),
    ("studio", "Studio Construction cost with furnishing", "Studio"),
    ("plot", "Plotted Construction Development Cost", "Plot"),
    ("inst", "Institutional Plotted Development Cost", "Institutional"),
    ("comm", "Commercial Construction Cost", "Commercial"),
    ("ews_dev", "EWS/LIG plots development cost", "EWS/LIG"),
]


# --------------------------------------------------------------------------------------------
# 2. THE BUILDING BLOCKS (one class per section of the INPUTS sheet)
# --------------------------------------------------------------------------------------------
@dataclass
class ProjectInfo:                                   # INPUTS Section 1
    name: str
    location: str
    project_type: str
    start_date: date                                 # must be a quarter-end date (= Q1)
    deal_type: str
    entity: str
    scenario: str
    lifecycle_override_years: Optional[float] = None # blank = use derived project span


@dataclass
class Land:                                          # INPUTS Section 2
    area_sqyd: float
    market_rate: float                               # Rs / sq yd
    dlc_rate_sqm: float                              # Rs / sq m (government guideline rate)
    lo_share: float                                  # JV: landowner revenue share
    stamp_duty_jv: float                             # JV: % of DLC value
    purchase_rate: float                             # Outright: Rs / sq yd
    stamp_duty_outright: float                       # Outright: % of max(DLC, price)
    payment_curve: str = "Upfront"                   # Outright land payment
    payment_start_q: int = 1
    payment_end_q: int = 1


@dataclass
class Scenario:                                      # INPUTS Section 3 (one row)
    name: str
    sales_period_mult: float                         # 1.5 = sales take 50% longer
    price_change: float                              # -0.075 = prices 7.5% lower
    cost_change: float                               # +0.075 = construction 7.5% dearer
    delay_q: int                                     # quarters added to fixed launch/start


@dataclass
class Zone:                                          # INPUTS Section 4 (one row)
    name: str
    share: float                                     # share of land area


@dataclass
class Timing:                                        # INPUTS Section 5B (one row)
    launch_mode: str = "Fixed quarter"
    launch_link_product: Optional[str] = None
    launch_link_event: Optional[str] = None
    launch_offset: int = 0
    cons_mode: str = "Fixed quarter"
    cons_link_product: Optional[str] = None
    cons_link_event: Optional[str] = None
    cons_offset: int = 0


@dataclass
class Product:                                       # INPUTS Section 5 (one row)
    name: str
    zone: str
    category: str
    include: bool                                    # "Include? (your choice)"
    area_sqft: float
    rate: float                                      # base sales rate, Rs / sq ft
    construction_rate: float                         # Rs / sq ft of saleable area
    launch_q: int                                    # used if launch is "Fixed quarter" (and as fallback)
    sales_period_q: int
    sales_curve: str
    clp_plan: str
    construction_start_q: int                        # used if construction is "Fixed quarter"
    construction_duration_q: int
    construction_curve: str
    timing: Timing = field(default_factory=Timing)


@dataclass
class CostHead:                                      # INPUTS Section 6 (one row)
    key: str                                         # internal id, e.g. "legal"
    name: str
    rate1: Optional[float] = None                    # "Rate / input 1"
    rate2: Optional[object] = None                   # "Input 2" (number or a basis name)
    applicable: bool = True
    curve: str = "Follow Construction"
    start_q: Optional[int] = None
    end_q: Optional[int] = None
    basis: Optional[str] = None                      # spare rows only


@dataclass
class BarCalc:                                       # INPUTS Section 7A
    authority: str
    land_use: str
    free_far: float
    loading_factor: float
    reserved_price_sqm: float
    gst_applicable: bool
    gst_rate: float
    pct_table: dict                                  # {land_use: {authority: pct or None}}


@dataclass
class AifCalc:                                       # INPUTS Section 7B
    rate: float
    tenure_years: float
    compounding: str


@dataclass
class InitialInvestment:                             # INPUTS Sections 7C & 7D
    advance_pct: float                               # JV advance to LO, % of market land value
    dd_amount: float                                 # Rs Cr, on due diligence
    da_amount: float                                 # Rs Cr, at DA (token = balance)
    legal_share: float                               # share of legal paid before DA
    bar_share: float                                 # share of BAR paid upfront
    dev_cost_pre_da: float                           # Rs Cr
    marketing_pre_launch: float                      # Rs Cr
    payout_q: dict                                   # item -> quarter number
    outright_construction_share: float               # Outright: % of built-up construction
    outright_legal_share: float                      # Outright: % of legal


@dataclass
class Milestone:                                     # INPUTS Section 8 (one row of a plan)
    name: str
    trigger: str                                     # "Booking + quarters" | "Construction % complete"
    value: float                                     # quarters after booking OR construction fraction
    pct: float                                       # share of sale value


@dataclass
class ClpPlan:
    name: str
    milestones: list


@dataclass
class Finance:                                       # INPUTS Section 9
    tax_company: float
    tax_llp: float
    cost_of_equity: float
    benchmarks: dict


@dataclass
class Project:                                       # the whole INPUTS sheet
    info: ProjectInfo
    land: Land
    scenarios: list
    zones: list
    products: list
    costs: list
    bar: BarCalc
    aif: AifCalc
    initial: InitialInvestment
    catch_up_lag: int
    plans: list
    finance: Finance

    # ---------- small helpers used everywhere ----------
    def active_products(self) -> list:
        """Products that are included AND belong to a zone allowed by the project type."""
        allowed = ZONES_FOR_TYPE.get(self.info.project_type, [])
        return [p for p in self.products if p.include and p.zone in allowed]

    def scenario(self) -> Scenario:
        return next(s for s in self.scenarios if s.name == self.info.scenario)

    def plan(self, name: str) -> ClpPlan:
        return next(p for p in self.plans if p.name == name)

    def cost(self, key: str) -> CostHead:
        return next(c for c in self.costs if c.key == key)


# --------------------------------------------------------------------------------------------
# 3. SAVE / LOAD (a project is stored as a readable JSON text file)
# --------------------------------------------------------------------------------------------
def to_dict(project: Project) -> dict:
    d = asdict(project)
    d["info"]["start_date"] = project.info.start_date.isoformat()
    return d


def from_dict(d: dict) -> Project:
    info = dict(d["info"]); info["start_date"] = date.fromisoformat(info["start_date"])
    products = []
    for p in d["products"]:
        p = dict(p); p["timing"] = Timing(**p["timing"]); products.append(Product(**p))
    plans = [ClpPlan(pl["name"], [Milestone(**m) for m in pl["milestones"]]) for pl in d["plans"]]
    return Project(
        info=ProjectInfo(**info), land=Land(**d["land"]),
        scenarios=[Scenario(**s) for s in d["scenarios"]], zones=[Zone(**z) for z in d["zones"]],
        products=products, costs=[CostHead(**c) for c in d["costs"]],
        bar=BarCalc(**d["bar"]), aif=AifCalc(**d["aif"]), initial=InitialInvestment(**d["initial"]),
        catch_up_lag=d["catch_up_lag"], plans=plans, finance=Finance(**d["finance"]))


def save_project(project: Project, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(to_dict(project), f, indent=2, ensure_ascii=False)


def load_project(path: str) -> Project:
    with open(path, encoding="utf-8") as f:
        return from_dict(json.load(f))


# --------------------------------------------------------------------------------------------
# 4. INPUT CHECKS (the Excel "Model checks" for inputs) - returns a list of plain-English errors
# --------------------------------------------------------------------------------------------
def _is_int(x) -> bool:
    return isinstance(x, (int, float)) and float(x).is_integer()


@dataclass
class Issue:
    section: str      # INPUTS section, e.g. "Products"
    item: str         # the field / row it belongs to, e.g. a product name or "start_date"
    message: str


def validate(project: Project) -> list:
    """Plain-English error list, e.g. ['[CLP] Plan 'X' totals 95.00% - it must be exactly 100%.']"""
    return [f"[{i.section}] {i.message}" for i in check_inputs(project)]


def check_inputs(project: Project) -> list:
    """Same checks as validate(), but each problem also says WHICH field/row caused it (used by the app
    to show the error right next to that field)."""
    errors = []
    def err(section, msg, item=""): errors.append(Issue(section, item, msg))
    i = project.info

    # Section 1 - project
    d = i.start_date
    if not (d.month in (3, 6, 9, 12) and (date(d.year + (d.month == 12), d.month % 12 + 1, 1) - d).days == 1):
        err("Project", f"Start date {d} is not a quarter-end date (31-Mar, 30-Jun, 30-Sep, 31-Dec).", "start_date")
    for val, allowed, label in [(i.project_type, PROJECT_TYPES, "Project type"), (i.deal_type, DEAL_TYPES, "Deal type"),
                                (i.entity, ENTITIES, "Taxable entity")]:
        if val not in allowed: err("Project", f"{label} '{val}' must be one of {allowed}.", label)
    if i.scenario not in [s.name for s in project.scenarios]:
        err("Project", f"Active scenario '{i.scenario}' is not in the scenario table.", "scenario")
    if i.lifecycle_override_years is not None and i.lifecycle_override_years <= 0:
        err("Project", "Lifecycle override must be blank or a positive number of years.", "lifecycle")

    # Section 2 - land
    L = project.land
    if L.area_sqyd <= 0 or L.market_rate <= 0 or L.dlc_rate_sqm <= 0:
        err("Land", "Land area, market rate and DLC rate must be greater than zero.", "land_rates")
    if i.deal_type == "JV" and not (0 <= L.lo_share < 1):
        err("Land", "Landowner share must be between 0% and 99.9%.", "lo_share")
    if i.deal_type == "Outright":
        if L.purchase_rate <= 0: err("Land", "Purchase rate must be greater than zero.", "purchase_rate")
        if L.payment_curve not in LAND_CURVES: err("Land", f"Land payment curve must be one of {LAND_CURVES}.", "payment")
        end = L.payment_start_q if L.payment_curve == "Upfront" else L.payment_end_q
        if not (_is_int(L.payment_start_q) and 1 <= L.payment_start_q <= end <= HORIZON_Q):
            err("Land", "Land payment start/end quarters must be whole numbers with 1 <= start <= end <= 40.", "payment")

    # Section 3 - scenarios
    names = [s.name for s in project.scenarios]
    if len(names) != len(set(names)): err("Scenarios", "Scenario names must be unique.", "names")
    for s in project.scenarios:
        if s.sales_period_mult <= 0 or s.price_change <= -1 or s.cost_change <= -1 or not (_is_int(s.delay_q) and s.delay_q >= 0):
            err("Scenarios", f"Scenario '{s.name}' has an invalid value.", s.name)

    # Section 4 - zones
    if sum(z.share for z in project.zones) > 1 + 1e-9 or any(z.share < 0 for z in project.zones):
        err("Zones", "Zone shares must be >= 0 and total at most 100%.", "zones")

    # Section 5 - products
    pnames = [p.name for p in project.products]
    if len(pnames) != len(set(pnames)): err("Products", "Every product needs a different name (needed for links).", "names")
    active = project.active_products()
    if not active: err("Products", "No product is active for this project type - include a product whose zone matches.", "active")
    plan_names = [pl.name for pl in project.plans]
    for idx, p in enumerate(project.products):
        if not p.include: continue
        tag = f"Product '{p.name}'"
        if p.zone not in ZONES: err("Products", f"{tag}: zone must be one of {ZONES}.", p.name)
        if p.category not in CATEGORIES: err("Products", f"{tag}: category must be one of {CATEGORIES}.", p.name)
        if p.area_sqft <= 0 or p.rate < 0 or p.construction_rate < 0:
            err("Products", f"{tag}: area must be > 0 and rates >= 0.", p.name)
        for val, label in [(p.sales_period_q, "sales period"), (p.construction_duration_q, "construction duration")]:
            if not (_is_int(val) and val >= 1): err("Products", f"{tag}: {label} must be a whole number >= 1.", p.name)
        if p.sales_curve not in BASIC_CURVES or p.construction_curve not in BASIC_CURVES:
            err("Products", f"{tag}: sales/construction curve must be one of {BASIC_CURVES}.", p.name)
        if p.clp_plan not in plan_names: err("Products", f"{tag}: payment plan '{p.clp_plan}' does not exist.", p.name)
        t = p.timing
        if t.launch_mode not in LAUNCH_MODES or t.cons_mode not in CONS_MODES:
            err("Timing", f"{tag}: invalid launch / construction timing mode.", p.name)
        if t.launch_mode == "After own construction start" and t.cons_mode == "After own launch":
            err("Timing", f"{tag}: launch and construction cannot both depend on each other (circular).", p.name)
        above = pnames[:idx]
        for mode, prod, ev, label in [(t.launch_mode, t.launch_link_product, t.launch_link_event, "launch"),
                                      (t.cons_mode, t.cons_link_product, t.cons_link_event, "construction")]:
            if mode == "Linked to another product":
                if prod not in above: err("Timing", f"{tag}: {label} is linked to '{prod}', which must be a product listed ABOVE it.", p.name)
                if ev not in LINK_EVENTS: err("Timing", f"{tag}: {label} link event must be one of {LINK_EVENTS}.", p.name)
        for val, label in [(p.launch_q, "fixed launch quarter"), (p.construction_start_q, "fixed construction start quarter")]:
            if not (_is_int(val) and val >= 1): err("Products", f"{tag}: {label} must be a whole number >= 1 (also used as fallback).", p.name)

    # Section 6 - cost heads
    keys = [c.key for c in project.costs]
    for c in project.costs:
        if c.curve not in COST_CURVES: err("Costs", f"'{c.name}': phasing curve must be one of {COST_CURVES}.", c.key); continue
        if c.curve in MANUAL_CURVES and c.applicable:
            end = c.start_q if c.curve == "Upfront" else c.end_q
            if not (_is_int(c.start_q) and _is_int(end) and 1 <= c.start_q <= end <= HORIZON_Q):
                err("Costs", f"'{c.name}': start/end quarters must be whole numbers with 1 <= start <= end <= 40.", c.key)
        if c.rate1 is not None and isinstance(c.rate1, (int, float)) and c.rate1 < 0:
            err("Costs", f"'{c.name}': rate cannot be negative.", c.key)
        if c.key.startswith("spare") and c.applicable and c.basis not in SPARE_BASES:
            err("Costs", f"'{c.name}': basis must be one of {SPARE_BASES}.", c.key)
    if "cont" in keys and project.cost("cont").rate2 not in CONTINGENCY_BASES:
        err("Costs", f"Contingency base must be one of {CONTINGENCY_BASES}.", "cont")
    if "edc" in keys and project.cost("edc").rate2 not in EDC_BASES:
        err("Costs", f"External development basis must be one of {EDC_BASES}.", "edc")

    # Section 7 - calculators
    b = project.bar
    if b.authority not in BAR_AUTHORITIES or b.land_use not in BAR_LAND_USES:
        err("BAR", "Authority / land use not recognised.", "bar")
    elif not b.pct_table.get(b.land_use, {}).get(b.authority):
        err("BAR", f"No BAR % defined for {b.authority} / {b.land_use} - combination not allowed.", "bar")
    if b.loading_factor <= 0: err("BAR", "Loading factor must be greater than zero.", "bar")
    if project.aif.compounding not in COMPOUNDING or project.aif.rate < 0 or project.aif.tenure_years < 0:
        err("AIF", "AIF rate / tenure / compounding invalid.", "aif")
    ii = project.initial
    advance = ii.advance_pct * L.area_sqyd * L.market_rate / CRORE
    if ii.dd_amount + ii.da_amount > advance + 1e-9:
        err("Initial investment", f"DD + DA instalments ({ii.dd_amount + ii.da_amount:.2f} Cr) exceed the total advance ({advance:.2f} Cr).", "dd_da")
    if any(not (_is_int(q) and 1 <= q <= HORIZON_Q) for q in ii.payout_q.values()):
        err("Initial investment", "Payout quarters must be whole numbers between 1 and 40.", "payout_q")

    # Section 8 - payment plans
    if not (_is_int(project.catch_up_lag) and 0 <= project.catch_up_lag <= 4):
        err("CLP", "Catch-up lag must be a whole number from 0 to 4.", "catch_up_lag")
    if len(plan_names) != len(set(plan_names)): err("CLP", "Payment plan names must be unique.", "plan_names")
    for pl in project.plans:
        total = sum(m.pct for m in pl.milestones)
        if abs(total - 1) > 1e-6: err("CLP", f"Plan '{pl.name}' totals {total:.2%} - it must be exactly 100%.", pl.name)
        for m in pl.milestones:
            if m.trigger == "Booking + quarters":
                if not (_is_int(m.value) and 0 <= m.value <= MAX_BOOKING_LAG):
                    err("CLP", f"Plan '{pl.name}', '{m.name}': booking lag must be a whole number 0-12.", pl.name)
            elif m.trigger == "Construction % complete":
                if not (0 <= m.value <= 1): err("CLP", f"Plan '{pl.name}', '{m.name}': construction trigger must be 0%-100%.", pl.name)
            else:
                err("CLP", f"Plan '{pl.name}', '{m.name}': trigger must be one of {TRIGGERS}.", pl.name)
            if m.pct < 0: err("CLP", f"Plan '{pl.name}', '{m.name}': % cannot be negative.", pl.name)

    # Section 9 - finance
    f = project.finance
    if not (0 <= f.tax_company < 1 and 0 <= f.tax_llp < 1 and f.cost_of_equity > 0):
        err("Finance", "Tax rates must be 0%-99.9% and cost of equity > 0.", "finance")
    return errors


# --------------------------------------------------------------------------------------------
# 5. THE SAMPLE PROJECT (identical to the Excel template "Project Aurora")
# --------------------------------------------------------------------------------------------
def sample_project() -> Project:
    T = Timing
    products = [
        Product("Villas", "Villa Development", "Villa", True, 250_000, 11_000, 2_900, 3, 8, "Front-loaded", "CLP – Villa", 4, 12, "S-curve",
                T("Fixed quarter", cons_mode="After own launch", cons_offset=1)),
        Product("Apartments – Towers A & B", "Apartment Development", "Apartment", True, 600_000, 7_500, 2_900, 4, 12, "Even", "CLP – Apartment", 5, 16, "S-curve",
                T("Linked to another product", "Villas", "Launch", 1, "After own launch", cons_offset=1)),
        Product("Studios", "Apartment Development", "Studio", True, 40_000, 9_000, 3_800, 6, 8, "Even", "CLP – Apartment", 6, 12, "S-curve",
                T("Linked to another product", "Apartments – Towers A & B", "Construction start", 1, "After own launch", cons_offset=0)),
        Product("High-street retail", "Apartment Development", "Commercial", True, 30_000, 14_000, 2_900, 8, 8, "Back-loaded", "Down Payment Plan", 6, 12, "S-curve",
                T("Linked to another product", "Apartments – Towers A & B", "Launch", 4,
                  "Linked to another product", "Apartments – Towers A & B", "Construction start", 1)),
        Product("Residential plots", "Plotted Development", "Plot", False, 150_000, 4_500, 450, 10, 8, "Even", "Plot – Development Linked", 9, 8, "Even"),
        Product("Institutional plots", "Plotted Development", "Institutional", False, 30_000, 4_000, 400, 12, 8, "Even", "Plot – Development Linked", 9, 8, "Even"),
        Product("EWS / LIG plots", "Plotted Development", "EWS/LIG", False, 20_000, 1_500, 400, 10, 8, "Even", "Plot – Development Linked", 9, 8, "Even"),
    ]
    C = CostHead
    costs = [
        C("land", "Land Cost", curve="Follow Collections"),
        C("sd", "Stamp Duty", curve="Upfront", start_q=1, end_q=1),
        C("brok", "Brokerage", rate1=0.0118, curve="Upfront", start_q=1, end_q=1),
    ] + [C(k, n, curve="Follow Construction") for k, n, _ in CONSTRUCTION_HEADS] + [
        C("ovh", "Corporate Overheads (Rs/Sq Ft SA)", rate1=0.04, curve="Follow Project Life"),
        C("mkt", "Marketing & Sales @ %", rate1=0.07, rate2=0.05, curve="Follow Sales"),
        C("legal", "Legal & Compliance (Rs/Sq Ft SA)", rate1=75, curve="Front-loaded", start_q=1, end_q=8),
        C("ews", "EWS / LIG @ Rs/Sq Ft (Builtup)", rate1=400, rate2=0.05, curve="Follow Construction"),
        C("cont", "Contingency @ %", rate1=0.0, rate2="Construction cost", curve="Follow Construction"),
        C("edc", "External Development & Landscaping", rate1=0.0, rate2="Rs/sq ft (total saleable area)", curve="Follow Construction"),
        C("hotel", "Hotel Brand Key fee Rs 50K per Key for smaller brand", rate1=50_000, rate2=0, curve="Follow Construction"),
        C("furn", "Furnishing Cost for Studios", rate1=500, applicable=False, curve="Follow Construction"),
        C("gst", "GST cost in case of commercial/Plotting development", rate1=0.18, rate2=0.20, applicable=False, curve="At Project End"),
        C("aif", "AIF Cost", applicable=False, curve="Follow Project Life"),
        C("bar", "BAR / Premium FAR Cost", curve="Upfront", start_q=2, end_q=2),
    ]
    B, M = "Booking + quarters", "Construction % complete"
    plans = [
        ClpPlan("CLP – Villa", [Milestone("Earnest money", B, 0, .10), Milestone("Agreement to sell (ATS)", B, 1, .10),
            Milestone("Commencement of construction", M, .05, .10), Milestone("Ground plinth", M, .15, .10),
            Milestone("First floor roof casting", M, .35, .15), Milestone("Second floor roof casting", M, .55, .15),
            Milestone("Third floor roof casting", M, .75, .15), Milestone("Completion certificate (CC)", M, .95, .05),
            Milestone("Possession", M, 1.0, .10)]),
        ClpPlan("CLP – Apartment", [Milestone("Booking amount", B, 0, .10), Milestone("Agreement to sell (ATS)", B, 1, .10),
            Milestone("Foundation completion", M, .10, .10), Milestone("Podium / plinth", M, .20, .10),
            Milestone("Slab casting – 25% floors", M, .35, .10), Milestone("Slab casting – 50% floors", M, .50, .10),
            Milestone("Slab casting – 75% floors", M, .65, .10), Milestone("Top slab casting", M, .80, .10),
            Milestone("Brickwork & plaster", M, .90, .05), Milestone("Flooring & finishing", M, .95, .05),
            Milestone("Possession", M, 1.0, .10)]),
        ClpPlan("Plot – Development Linked", [Milestone("Booking amount", B, 0, .10), Milestone("Agreement to sell (ATS)", B, 1, .20),
            Milestone("Roads & services start", M, .25, .20), Milestone("Services 60% complete", M, .60, .20),
            Milestone("Possession / registry", M, 1.0, .30)]),
        ClpPlan("Down Payment Plan", [Milestone("Booking amount", B, 0, .10), Milestone("Down payment", B, 1, .80),
            Milestone("Possession", M, 1.0, .10)]),
        ClpPlan("CLP – 17-Floor Tower", [Milestone("Booking amount", B, 0, .10), Milestone("Agreement to sell (ATS)", B, 1, .10),
            Milestone("Excavation", M, .03, .05), Milestone("Foundation / raft", M, .08, .05)]
            + [Milestone(f"Slab casting – floor {k}", M, round(0.12 + 0.03625 * (k - 1), 5), .025) for k in range(1, 18)]
            + [Milestone("Brickwork", M, .78, .05), Milestone("Plaster & MEP", M, .85, .05),
               Milestone("Flooring & finishing", M, .92, .075), Milestone("Possession", M, 1.0, .10)]),
    ]
    return Project(
        info=ProjectInfo("Project Aurora (Sample)", "Sample City, Rajasthan", "Mixed Development", date(2027, 6, 30), "JV", "Company", "Base Case"),
        land=Land(area_sqyd=30_000, market_rate=60_000, dlc_rate_sqm=13_000, lo_share=0.32, stamp_duty_jv=0.0275,
                  purchase_rate=60_000, stamp_duty_outright=0.088),
        scenarios=[Scenario("Best Case", 0.75, 0.05, 0.0, 0), Scenario("Base Case", 1.0, 0.0, 0.0, 0), Scenario("Worst Case", 1.5, -0.075, 0.075, 2)],
        zones=[Zone("Villa Development", 0.35), Zone("Apartment Development", 0.50), Zone("Plotted Development", 0.15), Zone("Other / Clubhouse", 0.0)],
        products=products, costs=costs,
        bar=BarCalc("JDA", "Residential", 2.0, 1.35, 12_000, False, 0.18,
                    {"Industrial": {"RIICO": 0.20, "JDA": None}, "Residential": {"RIICO": 0.30, "JDA": 0.20},
                     "Commercial": {"RIICO": 0.40, "JDA": 0.40}}),
        aif=AifCalc(0.18, 3, "Annually"),
        initial=InitialInvestment(0.10, 0.0, 0.0, 1.0, 0.25, 0.0, 0.0,
                                  {"token": 1, "dd": 1, "da": 2, "legal": 2, "dev": 2, "marketing": 2, "sd": 2, "brok": 2, "bar": 2},
                                  0.10, 0.10),
        catch_up_lag=1, plans=plans,
        finance=Finance(0.26, 0.35, 0.18, {"project_irr": 0.22, "developer_irr": 0.18, "equity_multiple": 2.0, "roce": 0.30,
                                           "cagr": 0.30, "pat_margin": 0.15, "ebitda_margin": 0.20}),
    )
