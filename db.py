"""db.py — Google Sheets leaderboard for IE105000 VRP game.

Worksheet: "vrp_routes"

Streamlit secrets (.streamlit/secrets.toml):
    gcp_json = '{...}'
    [sheet]
    id = "YOUR_SHEET_ID"
"""
from __future__ import annotations
import json
from datetime import datetime, timezone

import gspread
import streamlit as st
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SHEET_NAME = "IE105000_2"

HEADERS = [
    "id", "student_id", "student_name", "played_at",
    "total_distance", "reference_distance", "gap_pct", "score",
    "feasible", "v1_route", "v2_route", "n_violations",
    "seed", "num_vehicles", "num_shipments",
]


@st.cache_resource
def _get_spreadsheet():
    if "gcp_json" in st.secrets:
        creds_info = json.loads(st.secrets["gcp_json"])
    else:
        creds_info = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(st.secrets["sheet"]["id"])


def _ws():
    return _get_spreadsheet().worksheet(SHEET_NAME)


def init_db():
    sh = _get_spreadsheet()
    existing = [w.title for w in sh.worksheets()]
    if SHEET_NAME not in existing:
        ws = sh.add_worksheet(SHEET_NAME, rows=2000, cols=len(HEADERS) + 3)
        ws.update("A1", [HEADERS])
    else:
        ws = sh.worksheet(SHEET_NAME)
        first_row = ws.row_values(1)
        if first_row != HEADERS:
            ws.update("A1", [HEADERS])


def save_solution(student_name, evaluation, reference_dist, score,
                  student_id="", seed=None, num_vehicles=None, num_shipments=None):
    ws = _ws()
    rows = ws.get_all_records()
    new_id = max((int(r["id"]) for r in rows), default=0) + 1
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    rr = evaluation["route_results"]
    v1_route = " → ".join(rr["v1"]["stops"]) if "v1" in rr else ""
    v2_route = " → ".join(rr["v2"]["stops"]) if "v2" in rr else ""
    gap = round((evaluation["total_distance"] - reference_dist) / reference_dist * 100, 1) if reference_dist else 0

    row = [
        new_id, student_id.strip(), student_name.strip(), now,
        round(evaluation["total_distance"], 2),
        round(reference_dist, 2),
        gap, score,
        1 if evaluation["feasible"] else 0,
        v1_route, v2_route,
        len(evaluation["violations"]),
        seed if seed is not None else "",
        num_vehicles if num_vehicles is not None else "",
        num_shipments if num_shipments is not None else "",
    ]
    ws.append_row(row, value_input_option="RAW")
    get_leaderboard.clear()


@st.cache_data(ttl=60)
def get_leaderboard(top_n=50):
    rows = _ws().get_all_records()
    if not rows:
        return []

    best = {}
    plays = {}
    for r in rows:
        name = str(r["student_name"]).strip().lower()
        plays[name] = plays.get(name, 0) + 1
        try:
            sc = float(r["score"])
            feas = int(r.get("feasible", 0))
        except (ValueError, TypeError):
            continue
        if feas == 0:
            continue  # only rank feasible solutions
        if name not in best or sc > float(best[name]["score"]):
            best[name] = r

    ranked = sorted(best.values(), key=lambda r: (
        -float(r["score"]),
        -int(r.get("num_shipments") or 0),
        -int(r.get("num_vehicles") or 0),
    ))[:top_n]
    result = []
    for i, r in enumerate(ranked, 1):
        name_key = str(r["student_name"]).strip().lower()
        result.append({
            "rank": i,
            "student_name": str(r["student_name"]).strip(),
            "score": float(r["score"]),
            "total_distance": float(r["total_distance"]),
            "reference_distance": float(r["reference_distance"]),
            "gap_pct": float(r.get("gap_pct", 0)),
            "num_shipments": int(r.get("num_shipments") or 0),
            "num_vehicles": int(r.get("num_vehicles") or 0),
            "plays": plays.get(name_key, 1),
            "best_at": r["played_at"],
        })
    return result
