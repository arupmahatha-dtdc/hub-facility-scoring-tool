import streamlit as st
import pandas as pd
import sqlite3
import json

st.set_page_config(page_title="Facility Scoring Tool", layout="wide")

st.title("Facility Selection Scoring Tool")

# --- Database helpers ---
DB_PATH = "submissions.db"

def get_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def parse_float(text):
    try:
        return float(text) if isinstance(text, str) and text.strip() != "" else None
    except Exception:
        return None

def parse_int(text):
    try:
        return int(text) if isinstance(text, str) and text.strip() != "" else None
    except Exception:
        return None

def float_input(label: str, placeholder: str = ""):
    raw = st.text_input(label, value="", placeholder=placeholder)
    return parse_float(raw)

def int_input(label: str, placeholder: str = ""):
    raw = st.text_input(label, value="", placeholder=placeholder)
    return parse_int(raw)

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            facility_code TEXT,
            employee_id TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            drive_link TEXT,
            total_score REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            payload TEXT
        )
        """
    )
    # Best-effort add of payload and facility_code columns if table exists without them
    try:
        cur.execute("ALTER TABLE submissions ADD COLUMN payload TEXT")
        conn.commit()
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE submissions ADD COLUMN facility_code TEXT")
        conn.commit()
    except Exception:
        pass
    conn.commit()
    conn.close()

init_db()

# --- Submission Inputs ---
st.header("Submit Facility Proposal")
facility_code = st.text_input("Facility Code", max_chars=64)
employee_id = st.text_input("Submitter ID or Name", max_chars=64)
col1, col2 = st.columns(2)
with col1:
    latitude_input = st.text_input("Latitude", placeholder="e.g., 28.6139")
with col2:
    longitude_input = st.text_input("Longitude", placeholder="e.g., 77.2090")
drive_link = st.text_input("Google Drive link (documents/videos)")

if 'last_submission' not in st.session_state:
    st.session_state['last_submission'] = None

# Category 1: Need Identification Strategy
st.header("1. Need Identification Strategy")

scenario = st.selectbox(
    "Which scenario triggers the need for a new facility?",
    ("", "Overutilization of existing facility", "External factors (e.g., political, natural)", "Network restructuring (optimization/addition/deletion)")
)

need_score = 0.0
if scenario == "Overutilization of existing facility":
    util = int_input("Current space utilization (%)", placeholder="e.g., 80")
    process_improve = st.checkbox("Possible to improve internal processes/layout to increase utilization?")
    bypass_plan = st.checkbox("Possible to implement a network bypass or mesh plan?")
    util_score = min((util or 0) / 100.0, 1.0)
    if process_improve:
        util_score *= 0.6
    if bypass_plan:
        util_score *= 0.8
    need_score = util_score * 10  # Category weight 10
elif scenario == "External factors (e.g., political, natural)":
    ext_planned = st.radio("Change nature", ("Planned", "Sudden/Unplanned"))
    ext_score = 0.5 if ext_planned == "Planned" else 1.0
    need_score = ext_score * 10
elif scenario == "Network restructuring (optimization/addition/deletion)":
    restructure = st.multiselect(
        "Network restructuring reasons (select all that apply):",
        ["Network optimization", "Long-haul planning change", "Add new facility", "Remove facility"]
    )
    res_score = 1.0 if restructure else 0.0
    need_score = res_score * 10
else:
    st.write("Select a scenario to calculate Need Identification score.")

st.write(f"Need Identification Score: {need_score:.1f} / 10")

# Category 2: Operation/Network Need
st.header("2. Operations and Network Needs")

ops = st.multiselect(
    "Operations required (select all that apply):",
    ["Air Operation", "Surface Express", "Surface LTL", "Unified Operations", "Branch", "Dark Store", "Origin Processing Unit (RTO/DP)"]
)

hubs_radius = int_input("Number of existing hubs within 20 km radius", placeholder="e.g., 0")
hubs_score = 1.0 if (hubs_radius is not None and hubs_radius <= 1) else 0.0

if "Air Operation" in ops:
    airport_dist = float_input("Distance to nearest major airport (km)", placeholder="e.g., 20.0")
    air_score = 1.0 if (airport_dist is not None and airport_dist <= 15.0) else 0.0
else:
    air_score = 0.0

if any(o in ops for o in ["Surface Express", "Surface LTL", "Unified Operations"]):
    highway_dist = float_input("Distance to nearest major highway (km)", placeholder="e.g., 20.0")
    highway_score = 1.0 if (highway_dist is not None and highway_dist <= 15.0) else 0.0
else:
    highway_score = 0.0

# Cost inputs: proposed vs budget; score based on budget/proposed ratio (capped 1.0)
budget_cost_sft = float_input("Budgeted rental cost per sq.ft (in local currency)", placeholder="e.g., 45.0")
cost_sft = float_input("Proposed rental cost per sq.ft (in local currency)", placeholder="e.g., 50.0")
if (budget_cost_sft is not None) and (cost_sft is not None) and cost_sft > 0:
    cost_ratio = budget_cost_sft / cost_sft
    cost_score = max(0.0, min(cost_ratio, 1.0))
else:
    cost_ratio = None
    cost_score = 0.0

op_weights = (
    (1.0 if "Air Operation" in ops else 0.0) +
    (1.0 if any(o in ops for o in ["Surface Express", "Surface LTL", "Unified Operations"]) else 0.0) +
    1.0 + 1.0
)
score_sum = hubs_score + air_score + highway_score + cost_score
ops_score = (score_sum / op_weights) * 20 if op_weights > 0 else 0.0

st.write(f"Operations/Network Needs Score: {ops_score:.1f} / 20")

# Category 3: Location Strategy
st.header("3. Location Strategy")

log_clusters = st.checkbox("Located within an existing logistics cluster area")
infra_future = st.checkbox("Future transportation infrastructure (planned highways/rails) is nearby")
connect_highway = st.checkbox("Connected to a major highway within 15 km")
hazard_free = st.checkbox("Not in a known natural hazard zone (e.g. flood, earthquake)")
zoning_ok = st.checkbox("Zoning permits logistics operations")
utilities_ready = st.checkbox("Essential utilities (power, water, telecom, large vehicle access) are available")
support_services = st.checkbox("Support services (fuel, maintenance, driver facilities) are nearby")
labor_available = st.checkbox("Adequate local labor available without major union disputes")

loc_scores = [
    log_clusters, infra_future, connect_highway,
    hazard_free, zoning_ok, utilities_ready,
    support_services, labor_available
]
loc_score = sum([1 for s in loc_scores if s]) / len(loc_scores) * 35
st.write(f"Location Strategy Score: {loc_score:.1f} / 35")

# Category 4: Facility Specifications
st.header("4. Facility Specifications and Requirements")

exp_life = int_input("Expected facility operational life (years)", placeholder="e.g., 5")
life_score = min((exp_life or 0), 5) / 5.0

req_area = int_input("Forecasted minimum facility area required (sq.ft)", placeholder="e.g., 100000")
area_score = 1.0 if (req_area is not None and req_area >= 100000) else 0.0

clear_height = float_input("Clear height required (ft)", placeholder="e.g., 30.0")
height_score = 1.0 if (clear_height is not None and clear_height >= 30.0) else 0.0

skylight_score = 1.0 if st.checkbox("Facility has skylights covering 3-5% of roof") else 0.0
vent_score = 1.0 if st.checkbox("Facility has ridge ventilators (6-10 per 10,000 sq.ft.)") else 0.0
pillar_width = float_input("Distance between columns (width-wise, ft)", placeholder="e.g., 30.0")
pillar_score = 1.0 if (pillar_width is not None and pillar_width >= 25.0) else 0.0
pillar_length = float_input("Distance between columns (length-wise, ft)", placeholder="e.g., 80.0")
pillarL_score = 1.0 if (pillar_length is not None and pillar_length >= 75.0) else 0.0
floor_load = float_input("Floor load capacity (tons/sq.m)", placeholder="e.g., 6.0")
floor_score = 1.0 if (floor_load is not None and floor_load >= 5.0) else 0.0

docks = int_input("Number of dock doors", placeholder="e.g., 0")
# Informational dock counts (no scoring)
docks_over_50ft = int_input("Number of docks for vehicles >= 50 ft (info)", placeholder="e.g., 4")
docks_32ft = int_input("Number of docks for >= 32 ft vehicles (info)", placeholder="e.g., 6")
if req_area and req_area > 0:
    recommended_docks = req_area / 2500.0
    if docks is None:
        docks_score = 0.0
    else:
        docks_score = 1.0 if docks >= recommended_docks else (docks / recommended_docks if recommended_docks > 0 else 0.0)
else:
    docks_score = 0.0

enclosed_pct = int_input("Percentage of enclosed dock doors", placeholder="e.g., 20")
enclosed_score = 1.0 if (enclosed_pct is not None and enclosed_pct >= 10) else 0.0
dock_height = float_input("Dock height (ft)", placeholder="e.g., 14.0")
dockh_score = 1.0 if (dock_height is not None and 10.0 <= dock_height <= 15.0) else 0.0
leveller_pct = int_input("Percentage of docks with dock levellers", placeholder="e.g., 50")
leveller_score = 1.0 if (leveller_pct is not None and leveller_pct >= 50) else 0.0
canopy_len = float_input("Canopy length over dock (ft)", placeholder="e.g., 15.0")
canopy_score = 1.0 if (canopy_len is not None and canopy_len >= 15.0) else 0.0
clearance_height = float_input("Clearance height from dock apron (ft)", placeholder="e.g., 18.0")
clear_score = 1.0 if (clearance_height is not None and clearance_height >= 18.0) else 0.0
side_clearance = float_input("Side clearance from dock doors (ft)", placeholder="e.g., 10.0")
side_score = 1.0 if (side_clearance is not None and side_clearance >= 10.0) else 0.0
tail_score = 1.0 if st.checkbox("Trucks can tail-mate at 90° angle at docks") else 0.0
dual_score = 1.0 if st.checkbox("Dual-sided (opposite) dock operations possible") else 0.0
# Apron clearance informational only (no score)
apron_clearance = float_input("Apron clearance distance for HCVs (ft) greater than 70 ft (info)", placeholder="e.g., 70.0")
hcv_slots = int_input("Dedicated HCV parking slots", placeholder="e.g., 6")
hcv_score = 1.0 if (hcv_slots is not None and hcv_slots >= 6) else 0.0
mcv_slots = int_input("Dedicated MCV/LCV parking slots", placeholder="e.g., 10")
mcv_score = 1.0 if (mcv_slots is not None and mcv_slots >= 10) else 0.0
car_slots = int_input("Employee car parking slots", placeholder="e.g., 5")
two_wheeler_slots = int_input("Employee two-wheeler parking slots", placeholder="e.g., 50")
parking_score = 1.0 if (car_slots is not None and car_slots >= 4 and two_wheeler_slots is not None and two_wheeler_slots >= 40) else 0.0
fire_score = 1.0 if st.checkbox("Facility fire safety (sprinklers, hydrants) compliant") else 0.0
office_space_pct = float_input("Office space (% of total area)", placeholder="e.g., 4.0")
office_score = 1.0 if (office_space_pct is not None and 3.0 <= office_space_pct <= 5.0) else 0.0
fiber_score = 1.0 if st.checkbox("High-speed fiber network connectivity ready") else 0.0
driver_score = 1.0 if st.checkbox("Dedicated driver rest area with basic facilities") else 0.0
beds = int_input("Driver rest room bed capacity", placeholder="e.g., 5")
beds_score = 1.0 if (beds is not None and beds >= 5) else 0.0

# Plinth details (informational)
plinth_height = float_input("Plinth height (ft) (info)", placeholder="e.g., 4.0")
plinth_uniform = st.checkbox("Is plinth height same across all docks? (info)")

spec_scores = [
    life_score, area_score, height_score, skylight_score, vent_score,
    pillar_score, pillarL_score, floor_score, docks_score, enclosed_score,
    dockh_score, leveller_score, canopy_score, clear_score, side_score,
    tail_score, dual_score, hcv_score, mcv_score,
    parking_score, fire_score, office_score, fiber_score, driver_score, beds_score
]
facility_score = (sum(spec_scores) / len(spec_scores)) * 35
st.write(f"Facility Specifications Score: {facility_score:.1f} / 35")

# Final Score
total_score = need_score + ops_score + loc_score + facility_score
st.header(f"Total Facility Score: {total_score:.1f} / 100")

# Score summary DataFrame and export
data = {
    "Category": ["Need Identification", "Operations/Network", "Location Strategy", "Facility Specs", "Total Score"],
    "Score": [need_score, ops_score, loc_score, facility_score, total_score]
}
df_score = pd.DataFrame(data)

st.subheader("Score Summary")
st.write(f"Need Identification: {need_score:.1f} / 10")
st.write(f"Operations/Network: {ops_score:.1f} / 20")
st.write(f"Location Strategy: {loc_score:.1f} / 35")
st.write(f"Facility Specs: {facility_score:.1f} / 35")

# Save submission after score is computed
# Bottom submission button
st.write("")
submit_clicked = st.button("Submit Proposal")

if submit_clicked:
    # Build full payload
    # Parse compulsory numeric fields
    lat_value = None
    lon_value = None
    try:
        lat_value = float(latitude_input) if latitude_input.strip() != "" else None
    except Exception:
        lat_value = None
    try:
        lon_value = float(longitude_input) if longitude_input.strip() != "" else None
    except Exception:
        lon_value = None

    payload = {
        "submitter": {
            "facility_code": facility_code.strip(),
            "employee_id": employee_id.strip(),
            "latitude": lat_value,
            "longitude": lon_value,
            "drive_link": drive_link.strip(),
        },
        "need_identification": {
            "scenario": scenario,
            "util": 'util' in locals() and util or None,
            "process_improve": 'process_improve' in locals() and process_improve or None,
            "bypass_plan": 'bypass_plan' in locals() and bypass_plan or None,
            "ext_planned": 'ext_planned' in locals() and ext_planned or None,
            "restructure": 'restructure' in locals() and restructure or None,
            "need_score": need_score,
        },
        "operations_network": {
            "ops_selected": ops,
            "hubs_radius": hubs_radius,
            "airport_dist": 'airport_dist' in locals() and airport_dist or None,
            "highway_dist": 'highway_dist' in locals() and highway_dist or None,
            "budget_cost_sft": budget_cost_sft,
            "proposed_cost_sft": cost_sft,
            "cost_ratio_budget_to_proposed": cost_ratio,
            "ops_score": ops_score,
        },
        "location_strategy": {
            "log_clusters": log_clusters,
            "infra_future": infra_future,
            "connect_highway": connect_highway,
            "hazard_free": hazard_free,
            "zoning_ok": zoning_ok,
            "utilities_ready": utilities_ready,
            "support_services": support_services,
            "labor_available": labor_available,
            "loc_score": loc_score,
        },
        "facility_specs": {
            "exp_life": exp_life,
            "req_area": req_area,
            "clear_height": clear_height,
            "skylight": bool('skylight_score' in locals() and skylight_score),
            "vent": bool('vent_score' in locals() and vent_score),
            "pillar_width": pillar_width,
            "pillar_length": pillar_length,
            "floor_load": floor_load,
            "docks": docks,
            "docks_over_50ft_info": docks_over_50ft,
            "docks_32ft_info": docks_32ft,
            "recommended_docks": (req_area / 2500.0) if (req_area is not None and req_area > 0) else None,
            "enclosed_pct": enclosed_pct,
            "dock_height": dock_height,
            "leveller_pct": leveller_pct,
            "canopy_len": canopy_len,
            "clearance_height": clearance_height,
            "side_clearance": side_clearance,
            "tail_mate": bool('tail_score' in locals() and tail_score),
            "dual_sided": bool('dual_score' in locals() and dual_score),
            "apron_clearance_info": apron_clearance,
            "hcv_slots": hcv_slots,
            "mcv_slots": mcv_slots,
            "car_slots": car_slots,
            "two_wheeler_slots": two_wheeler_slots,
            "fire_compliant": bool('fire_score' in locals() and fire_score),
            "office_space_pct": office_space_pct,
            "fiber_ready": bool('fiber_score' in locals() and fiber_score),
            "driver_area": bool('driver_score' in locals() and driver_score),
            "beds": beds,
            "plinth_height_info": plinth_height,
            "plinth_uniform_info": plinth_uniform,
            "facility_score": facility_score,
        },
        "totals": {"total_score": total_score},
    }
    # Validation for compulsory fields
    errors = []
    if not facility_code.strip():
        errors.append("Facility Code is required.")
    if not employee_id.strip():
        errors.append("Employee ID is required.")
    if lat_value is None:
        errors.append("Latitude is required and must be a number.")
    if lon_value is None:
        errors.append("Longitude is required and must be a number.")

    if errors:
        for e in errors:
            st.error(e)
    else:
        try:
            conn = get_connection()
            cur = conn.cursor()
            # Check if a submission already exists for this facility_code
            cur.execute("SELECT id FROM submissions WHERE facility_code = ? ORDER BY datetime(created_at) DESC, id DESC LIMIT 1", (facility_code.strip(),))
            row = cur.fetchone()
            if row:
                # Update existing record
                cur.execute(
                    """
                    UPDATE submissions
                    SET employee_id = ?, latitude = ?, longitude = ?, drive_link = ?, total_score = ?, payload = ?, created_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (employee_id.strip(), float(lat_value), float(lon_value), drive_link.strip(), float(total_score), json.dumps(payload), int(row[0]))
                )
            else:
                # Insert new record
                cur.execute(
                    "INSERT INTO submissions (facility_code, employee_id, latitude, longitude, drive_link, total_score, payload) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (facility_code.strip(), employee_id.strip(), float(lat_value), float(lon_value), drive_link.strip(), float(total_score), json.dumps(payload))
                )
            conn.commit()
            conn.close()
            st.session_state['last_submission'] = employee_id.strip()
            st.success("Submission saved successfully.")
        except Exception as e:
            st.error(f"Failed to save submission: {e}")

# (duplicate form removed)