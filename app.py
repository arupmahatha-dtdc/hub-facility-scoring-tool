import streamlit as st
import pandas as pd

st.set_page_config(page_title="Facility Scoring Tool", layout="wide")

st.title("Facility Selection Scoring Tool")

# Category 1: Need Identification Strategy
st.header("1. Need Identification Strategy")

scenario = st.selectbox(
    "Which scenario triggers the need for a new facility?",
    ("", "Overutilization of existing facility", "External factors (e.g., political, natural)", "Network restructuring (optimization/addition/deletion)")
)

need_score = 0.0
if scenario == "Overutilization of existing facility":
    util = st.number_input("Current space utilization (%)", min_value=0, max_value=200, value=80)
    process_improve = st.checkbox("Possible to improve internal processes/layout to increase utilization?")
    bypass_plan = st.checkbox("Possible to implement a network bypass or mesh plan?")
    util_score = min(util / 100.0, 1.0)
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

hubs_radius = st.number_input("Number of existing hubs within 20 km radius", min_value=0, step=1, value=0)
hubs_score = 1.0 if hubs_radius <= 1 else 0.0

if "Air Operation" in ops:
    airport_dist = st.number_input("Distance to nearest major airport (km)", min_value=0.0, value=20.0)
    air_score = 1.0 if airport_dist <= 15.0 else 0.0
else:
    air_score = 0.0

if any(o in ops for o in ["Surface Express", "Surface LTL", "Unified Operations"]):
    highway_dist = st.number_input("Distance to nearest major highway (km)", min_value=0.0, value=20.0)
    highway_score = 1.0 if highway_dist <= 15.0 else 0.0
else:
    highway_score = 0.0

cost_sft = st.number_input("Proposed rental cost per sq.ft (in local currency)", min_value=0.0, value=50.0)
cost_score = 1.0 if cost_sft <= 100.0 else 0.0

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

exp_life = st.number_input("Expected facility operational life (years)", min_value=1, value=5)
life_score = min(exp_life, 5) / 5.0

req_area = st.number_input("Forecasted minimum facility area required (sq.ft)", min_value=0)
area_score = 1.0 if req_area >= 100000 else 0.0

clear_height = st.number_input("Clear height required (ft)", min_value=0.0, value=30.0)
height_score = 1.0 if clear_height >= 30.0 else 0.0

skylight_score = 1.0 if st.checkbox("Facility has skylights covering 3-5% of roof") else 0.0
vent_score = 1.0 if st.checkbox("Facility has ridge ventilators (6-10 per 10,000 sq.ft.)") else 0.0
pillar_score = 1.0 if st.number_input("Distance between columns (width-wise, ft)", 0.0, value=30.0) >= 25.0 else 0.0
pillarL_score = 1.0 if st.number_input("Distance between columns (length-wise, ft)", 0.0, value=80.0) >= 75.0 else 0.0
floor_score = 1.0 if st.number_input("Floor load capacity (tons/sq.m)", 0.0, value=6.0) >= 5.0 else 0.0

docks = st.number_input("Number of dock doors", min_value=0, value=0)
if req_area > 0:
    recommended_docks = req_area / 2500.0
    docks_score = 1.0 if docks >= recommended_docks else docks / recommended_docks if recommended_docks > 0 else 0.0
else:
    docks_score = 0.0

enclosed_score = 1.0 if st.number_input("Percentage of enclosed dock doors", 0, 100, 20) >= 10 else 0.0
dockh_score = 1.0 if 10.0 <= st.number_input("Dock height (ft)", 0.0, value=14.0) <= 15.0 else 0.0
leveller_score = 1.0 if st.number_input("Percentage of docks with dock levellers", 0, 100, 50) >= 50 else 0.0
canopy_score = 1.0 if st.number_input("Canopy length over dock (ft)", 0.0, value=15.0) >= 15.0 else 0.0
clear_score = 1.0 if st.number_input("Clearance height from dock apron (ft)", 0.0, value=18.0) >= 18.0 else 0.0
side_score = 1.0 if st.number_input("Side clearance from dock doors (ft)", 0.0, value=10.0) >= 10.0 else 0.0
tail_score = 1.0 if st.checkbox("Trucks can tail-mate at 90° angle at docks") else 0.0
dual_score = 1.0 if st.checkbox("Dual-sided (opposite) dock operations possible") else 0.0
apron_score = 1.0 if st.number_input("Apron clearance distance for HCVs (ft)", 0.0, value=70.0) >= 70.0 else 0.0
hcv_score = 1.0 if st.number_input("Dedicated HCV parking slots", 0, value=6) >= 6 else 0.0
mcv_score = 1.0 if st.number_input("Dedicated MCV/LCV parking slots", 0, value=10) >= 10 else 0.0
parking_score = 1.0 if (st.number_input("Employee car parking slots", 0, value=5) >= 4 and st.number_input("Employee two-wheeler parking slots", 0, value=50) >= 40) else 0.0
fire_score = 1.0 if st.checkbox("Facility fire safety (sprinklers, hydrants) compliant") else 0.0
office_score = 1.0 if 3.0 <= st.number_input("Office space (% of total area)", 0.0, value=4.0) <= 5.0 else 0.0
fiber_score = 1.0 if st.checkbox("High-speed fiber network connectivity ready") else 0.0
driver_score = 1.0 if st.checkbox("Dedicated driver rest area with basic facilities") else 0.0
beds_score = 1.0 if st.number_input("Driver rest room bed capacity", 0, value=5) >= 5 else 0.0

spec_scores = [
    life_score, area_score, height_score, skylight_score, vent_score,
    pillar_score, pillarL_score, floor_score, docks_score, enclosed_score,
    dockh_score, leveller_score, canopy_score, clear_score, side_score,
    tail_score, dual_score, apron_score, hcv_score, mcv_score,
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
# ✅ FIX: Use newer hide API if available
try:
    st.dataframe(df_score.style.hide(axis="index"))
except Exception:
    st.dataframe(df_score, hide_index=True)

csv = df_score.to_csv(index=False).encode('utf-8')
st.download_button(
    label="Download Scores as CSV",
    data=csv,
    file_name='facility_scores.csv',
    mime='text/csv'
)