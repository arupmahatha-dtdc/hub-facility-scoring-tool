import streamlit as st
import pandas as pd
import sqlite3
import json

DB_PATH = "submissions.db"

def get_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

st.set_page_config(page_title="Facility Scoring Dashboard", layout="wide")
st.title("Facility Scoring Dashboard")

# Load distinct facility codes for filter options
conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT DISTINCT COALESCE(facility_code, '') AS facility_code FROM submissions ORDER BY facility_code")
facility_options = [r[0] for r in cur.fetchall() if r[0] is not None and r[0] != ""]

# Multi-select filter (empty -> show all)
selected_facilities = st.multiselect("Filter by Facility Code(s)", options=facility_options)

# Fetch submissions
cur.execute(
    """
    WITH ranked AS (
        SELECT
            id, facility_code, employee_id, latitude, longitude, drive_link,
            total_score, created_at, payload,
            ROW_NUMBER() OVER (PARTITION BY facility_code ORDER BY datetime(created_at) DESC, id DESC) AS rn
        FROM submissions
    )
    SELECT id, facility_code, employee_id, latitude, longitude, drive_link,
           total_score, created_at, payload
    FROM ranked
    WHERE rn = 1
    ORDER BY datetime(created_at) DESC, id DESC
    """
)
rows = cur.fetchall()
cols = [d[0] for d in cur.description]
conn.close()

df = pd.DataFrame(rows, columns=cols)
if selected_facilities:
    df = df[df["facility_code"].isin(selected_facilities)]

# Build summary table: basic details + category scores + total
def extract_scores(payload_json):
    try:
        p = json.loads(payload_json) if isinstance(payload_json, str) and payload_json else {}
    except Exception:
        p = {}
    need = (p.get("need_identification") or {}).get("need_score")
    ops = (p.get("operations_network") or {}).get("ops_score")
    loc = (p.get("location_strategy") or {}).get("loc_score")
    fac = (p.get("facility_specs") or {}).get("facility_score")
    total = (p.get("totals") or {}).get("total_score")
    return need, ops, loc, fac, total

if not df.empty:
    scores = df["payload"].apply(extract_scores)
    df[["need_score", "ops_score", "loc_score", "facility_score", "total_score_payload"]] = pd.DataFrame(scores.tolist(), index=df.index)

summary_df = (
    df[[
        "id", "facility_code", "employee_id", "latitude", "longitude", "created_at",
        "need_score", "ops_score", "loc_score", "facility_score"
    ]].copy() if not df.empty else pd.DataFrame(columns=[
        "id", "facility_code", "employee_id", "latitude", "longitude", "created_at",
        "need_score", "ops_score", "loc_score", "facility_score"
    ])
)

# Prefer total_score from payload if present; fallback to stored total_score
if not df.empty:
    summary_df["total_score"] = df["total_score_payload"].where(df["total_score_payload"].notna(), df["total_score"])  # type: ignore
else:
    summary_df["total_score"] = []

st.subheader("Submissions")
# Add in-table checkbox for selection
selected_ids = []
if not summary_df.empty:
    table_df = summary_df.copy()
    table_df.insert(0, "select", False)
    edited_df = st.data_editor(
        table_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "select": st.column_config.CheckboxColumn("Select", default=False),
        },
        key="submissions_table_editor",
    )
    try:
        selected_ids = [int(x) for x in edited_df[edited_df["select"] == True]["id"].tolist()]
    except Exception:
        selected_ids = []
else:
    st.info("No submissions found.")

# Selection for download
st.markdown("")
st.subheader("Download Selected Submissions' Inputs as CSV")
if not summary_df.empty:
    # If no rows selected, default to all filtered
    if not selected_ids:
        selected_ids = summary_df["id"].tolist()

    # Build CSV of inputs (flattened payload)
    def row_to_payload_dict(row):
        try:
            p = json.loads(row["payload"]) if isinstance(row["payload"], str) and row["payload"] else {}
        except Exception:
            p = {}
        # Ensure some top-level basics exist even if payload missing
        submitter = p.get("submitter") or {}
        submitter.setdefault("facility_code", row.get("facility_code"))
        submitter.setdefault("employee_id", row.get("employee_id"))
        submitter.setdefault("latitude", row.get("latitude"))
        submitter.setdefault("longitude", row.get("longitude"))
        submitter.setdefault("drive_link", row.get("drive_link"))
        p["submitter"] = submitter
        return p

    filtered_df = df[df["id"].isin(selected_ids)] if selected_ids else df
    payload_dicts = [row_to_payload_dict(r) for _, r in filtered_df.iterrows()]
    if payload_dicts:
        flat = pd.json_normalize(payload_dicts, sep=".")
        # Keep a stable column order: basics first if present
        preferred_order = [
            "submitter.facility_code", "submitter.employee_id", "submitter.latitude",
            "submitter.longitude", "submitter.drive_link",
            "need_identification.need_score", "operations_network.ops_score",
            "location_strategy.loc_score", "facility_specs.facility_score",
            "totals.total_score",
        ]
        cols_in_flat = list(flat.columns)
        ordered = [c for c in preferred_order if c in cols_in_flat] + [c for c in cols_in_flat if c not in preferred_order]
        flat = flat[ordered]
        csv_bytes = flat.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download CSV",
            data=csv_bytes,
            file_name="facility_submissions_inputs.csv",
            mime="text/csv",
        )
    else:
        st.info("No data to download.")
else:
    st.info("No submissions found.")
