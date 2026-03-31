"""app.py — Streamlit UI for the IE105000 VRP Pickup & Delivery Game."""

import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

try:
    import db as _db
    _DB_AVAILABLE = True
except Exception:
    _DB_AVAILABLE = False

from engine import check_route, evaluate_solution, route_distance
from scenario import DEPOT, LOCATIONS, SHIPMENTS, VEHICLES
from solver import solve

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="VRP Pickup & Delivery Game — IE105000",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Color palette ─────────────────────────────────────────────────────────────
_C = {
    "bg":          "#0f172a",
    "grid":        "#1e293b",
    "depot":       "#93c5fd",
    "pickup":      "#fb923c",   # orange
    "delivery":    "#4ade80",   # green
    "v1":          "#60a5fa",   # blue
    "v2":          "#fbbf24",   # amber
    "unassigned":  "#94a3b8",
    "text":        "#f1f5f9",
    "subtext":     "#94a3b8",
    "border":      "#334155",
    "warn":        "#f87171",
    "ok":          "#4ade80",
    "card_bg":     "#1e293b",
}

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    .vrp-card {
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.75rem;
    }
    .vrp-card h4 { margin: 0 0 0.4rem 0; font-size: 1rem; color: #f1f5f9; }
    .vrp-card p  { margin: 0; font-size: 0.85rem; color: #94a3b8; }
    .route-v1 { border-left: 4px solid #60a5fa; }
    .route-v2 { border-left: 4px solid #fbbf24; }
    .warn-box {
        background: #1f0f0f;
        border: 1px solid #f87171;
        border-radius: 6px;
        padding: 0.5rem 0.75rem;
        margin: 0.3rem 0;
        font-size: 0.85rem;
        color: #fca5a5;
    }
    .ok-box {
        background: #0f1f0f;
        border: 1px solid #4ade80;
        border-radius: 6px;
        padding: 0.5rem 0.75rem;
        margin: 0.3rem 0;
        font-size: 0.85rem;
        color: #86efac;
    }
    .info-box {
        background: #0f172a;
        border: 1px solid #60a5fa;
        border-radius: 6px;
        padding: 0.5rem 0.75rem;
        margin: 0.3rem 0;
        font-size: 0.85rem;
        color: #93c5fd;
    }
    .score-big {
        font-size: 3rem;
        font-weight: 700;
        text-align: center;
        color: #f1f5f9;
    }
    .rank-medal { font-size: 1.4rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Cached solver ─────────────────────────────────────────────────────────────
@st.cache_data
def get_reference():
    return solve()


# ── Session state init ────────────────────────────────────────────────────────
def _init_state():
    if "vrp_routes" not in st.session_state:
        st.session_state.vrp_routes = {"v1": [], "v2": []}
    if "vrp_active_vehicle" not in st.session_state:
        st.session_state.vrp_active_vehicle = "v1"
    if "vrp_submitted" not in st.session_state:
        st.session_state.vrp_submitted = False
    if "vrp_evaluation" not in st.session_state:
        st.session_state.vrp_evaluation = None
    if "vrp_student_name" not in st.session_state:
        st.session_state.vrp_student_name = ""
    if "vrp_reference" not in st.session_state:
        st.session_state.vrp_reference = None
    if "vrp_active_tab" not in st.session_state:
        st.session_state.vrp_active_tab = 0
    if "vrp_score" not in st.session_state:
        st.session_state.vrp_score = 0


_init_state()


# ── Helper: which stops are assigned ─────────────────────────────────────────
def _assigned_to():
    """Returns dict: loc_id -> vehicle_id."""
    result = {}
    for vid, stops in st.session_state.vrp_routes.items():
        for s in stops:
            result[s] = vid
    return result


def _all_assigned():
    """True if every location is assigned to exactly one vehicle."""
    assigned = _assigned_to()
    return all(loc_id in assigned for loc_id in LOCATIONS)


def _current_load(vehicle_id):
    """Return current load carried at end of route (after all stops)."""
    stops = st.session_state.vrp_routes[vehicle_id]
    load = 0
    for sid in stops:
        loc = LOCATIONS[sid]
        shipment_id = loc["shipment"]
        if loc["type"] == "pickup":
            load += SHIPMENTS[shipment_id]["demand"]
        else:
            load -= SHIPMENTS[shipment_id]["demand"]
    return max(0, load)


def _compute_score(evaluation, reference_dist):
    if not evaluation["feasible"] or evaluation["total_distance"] == 0:
        return 0
    return min(1000, round(1000 * reference_dist / evaluation["total_distance"]))


# ── Map drawing ───────────────────────────────────────────────────────────────
def draw_map(routes, active_vehicle, highlight_clickable=True):
    """
    Returns a Plotly figure for the VRP map.

    Args:
        routes: {"v1": [stop_ids], "v2": [stop_ids]}
        active_vehicle: "v1" or "v2"
        highlight_clickable: whether to show clickable border for unassigned nodes
    """
    fig = go.Figure()

    assigned = {}
    for vid, stops in routes.items():
        for s in stops:
            assigned[s] = vid

    # ── 1. Dashed lines: shipment pairs (pickup ↔ delivery) ───────────────────
    for sid, sh in SHIPMENTS.items():
        p = LOCATIONS[sh["pickup"]]
        d = LOCATIONS[sh["delivery"]]
        fig.add_trace(go.Scatter(
            x=[p["x"], d["x"]],
            y=[p["y"], d["y"]],
            mode="lines",
            line=dict(color="#cbd5e1", width=1, dash="dot"),
            hoverinfo="skip",
            showlegend=False,
        ))

    # ── 2. Route lines for each vehicle ──────────────────────────────────────
    for vid, stop_ids in routes.items():
        if not stop_ids:
            continue
        veh = VEHICLES[vid]
        full_route = ["depot"] + list(stop_ids) + ["depot"]
        xs = []
        ys = []
        for loc_id in full_route:
            loc = DEPOT if loc_id == "depot" else LOCATIONS[loc_id]
            xs.append(loc["x"])
            ys.append(loc["y"])

        # Draw route line
        dist_val = route_distance(stop_ids)
        fig.add_trace(go.Scatter(
            x=xs,
            y=ys,
            mode="lines+markers",
            line=dict(color=veh["color"], width=2.5),
            marker=dict(
                symbol="arrow",
                size=10,
                color=veh["color"],
                angleref="previous",
            ),
            name=f"{veh['name']} ({dist_val:.2f} km)",
            showlegend=True,
            hoverinfo="skip",
        ))

    # ── 3. Location nodes ─────────────────────────────────────────────────────
    # Group nodes by render category for the scatter
    groups = {
        "v1":         {"xs": [], "ys": [], "texts": [], "hovers": [], "ids": [], "color": _C["v1"],    "symbol": "circle", "size": 16, "label": "V1 assigned"},
        "v2":         {"xs": [], "ys": [], "texts": [], "hovers": [], "ids": [], "color": _C["v2"],    "symbol": "circle", "size": 16, "label": "V2 assigned"},
        "pickup":     {"xs": [], "ys": [], "texts": [], "hovers": [], "ids": [], "color": _C["pickup"], "symbol": "circle", "size": 14, "label": "Pickup (unassigned)"},
        "delivery":   {"xs": [], "ys": [], "texts": [], "hovers": [], "ids": [], "color": _C["delivery"], "symbol": "diamond", "size": 14, "label": "Delivery (unassigned)"},
    }

    for loc_id, loc in LOCATIONS.items():
        sh = SHIPMENTS[loc["shipment"]]
        hover = (
            f"<b>{loc['icon']} {loc['name']}</b><br>"
            f"Type: {loc['type'].capitalize()}<br>"
            f"Shipment: {sh['name']} ({loc['shipment']})<br>"
            f"Coords: ({loc['x']}, {loc['y']})"
        )
        if loc_id in assigned:
            vid = assigned[loc_id]
            g = groups[vid]
        else:
            g = groups[loc["type"]]
        g["xs"].append(loc["x"])
        g["ys"].append(loc["y"])
        g["texts"].append(loc_id)
        g["hovers"].append(hover)
        g["ids"].append(loc_id)

    for gname, g in groups.items():
        if not g["xs"]:
            continue
        # Border color for clickable unassigned nodes
        if highlight_clickable and gname in ("pickup", "delivery"):
            line_color = _C["pickup"] if gname == "pickup" else _C["delivery"]
            line_width = 2
        else:
            line_color = "#0f172a"
            line_width = 1.5

        fig.add_trace(go.Scatter(
            x=g["xs"],
            y=g["ys"],
            mode="markers",
            marker=dict(
                symbol=g["symbol"],
                size=g["size"],
                color=g["color"],
                opacity=0.9,
                line=dict(color=line_color, width=line_width),
            ),
            customdata=[[cid] for cid in g["ids"]],
            hovertext=g["hovers"],
            hoverinfo="text",
            name=g["label"],
            showlegend=True,
        ))

    # ── 4. Depot node ─────────────────────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=[DEPOT["x"]],
        y=[DEPOT["y"]],
        mode="markers",
        marker=dict(
            symbol="square",
            size=20,
            color=_C["depot"],
            line=dict(color="#0f172a", width=2),
        ),
        customdata=[["depot"]],
        hovertext=[f"<b>🏭 {DEPOT['name']}</b><br>Depot (start/end)<br>Coords: ({DEPOT['x']}, {DEPOT['y']})"],
        hoverinfo="text",
        name="Depot",
        showlegend=True,
    ))

    # ── 5. Node annotations (labels outside markers) ─────────────────────────
    annotations = []

    # Depot label
    annotations.append(dict(
        x=DEPOT["x"], y=DEPOT["y"] - 0.55,
        text=f"<b>{DEPOT['name']}</b>",
        showarrow=False,
        font=dict(size=10, color=_C["depot"]),
        bgcolor="rgba(15,23,42,0.85)",
        borderpad=2,
    ))

    # Location labels
    for loc_id, loc in LOCATIONS.items():
        # Smart label placement: avoid overlap with depot
        dx = 0
        dy = 0.55
        # Push label away from depot
        if loc["y"] < DEPOT["y"]:
            dy = -0.55
        if loc["x"] < 1.5:
            dx = 0.3
        elif loc["x"] > 8.5:
            dx = -0.3

        if loc_id in assigned:
            vid = assigned[loc_id]
            fc = _C[vid]
        elif loc["type"] == "pickup":
            fc = _C["pickup"]
        else:
            fc = _C["delivery"]

        tag = "P" if loc["type"] == "pickup" else "D"
        label_text = f"<b>[{tag}] {loc['name']}</b>"

        annotations.append(dict(
            x=loc["x"] + dx,
            y=loc["y"] + dy,
            text=label_text,
            showarrow=False,
            font=dict(size=9, color=fc),
            bgcolor="rgba(15,23,42,0.85)",
            borderpad=2,
        ))

    fig.update_layout(
        annotations=annotations,
        plot_bgcolor=_C["bg"],
        paper_bgcolor=_C["bg"],
        xaxis=dict(
            range=[-0.2, 10.5],
            gridcolor=_C["grid"],
            gridwidth=1,
            dtick=1,
            title="x (km)",
            showline=True,
            linecolor=_C["border"],
            zeroline=False,
        ),
        yaxis=dict(
            range=[-0.2, 10.5],
            gridcolor=_C["grid"],
            gridwidth=1,
            dtick=1,
            title="y (km)",
            showline=True,
            linecolor=_C["border"],
            zeroline=False,
            scaleanchor="x",
            scaleratio=1,
        ),
        legend=dict(
            orientation="v",
            x=1.01, y=1,
            bgcolor="rgba(15,23,42,0.9)",
            bordercolor=_C["border"],
            borderwidth=1,
            font=dict(size=10),
        ),
        margin=dict(l=40, r=160, t=40, b=40),
        height=550,
        clickmode="event+select",
        dragmode=False,
        hovermode="closest",
    )

    return fig


# ── Route panel helper ────────────────────────────────────────────────────────
def _render_route_panel(vehicle_id):
    """Renders the route details panel for one vehicle."""
    veh = VEHICLES[vehicle_id]
    stops = st.session_state.vrp_routes[vehicle_id]
    color = veh["color"]
    cap = veh["capacity"]

    # Compute load profile
    load = 0
    load_ok = True
    picked_shipments = set()
    violations_local = []
    for sid in stops:
        loc = LOCATIONS[sid]
        sh_id = loc["shipment"]
        if loc["type"] == "pickup":
            load += SHIPMENTS[sh_id]["demand"]
            picked_shipments.add(sh_id)
            if load > cap:
                load_ok = False
                violations_local.append(f"Over capacity at {loc['name']}")
        else:
            if sh_id not in picked_shipments:
                violations_local.append(f"Delivery before pickup: {loc['name']}")
            else:
                load -= SHIPMENTS[sh_id]["demand"]

    dist_val = route_distance(stops) if stops else 0.0

    border_cls = f"route-{vehicle_id}"
    st.markdown(
        f'<div class="vrp-card {border_cls}">'
        f'<h4 style="color:{color}">🚚 {veh["name"]}</h4>'
        f'<p>Capacity: {len([s for s in stops if LOCATIONS[s]["type"]=="pickup"])}/{cap} shipments &nbsp;|&nbsp; '
        f'Distance: {dist_val:.2f} km</p>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if not stops:
        st.markdown('<p style="color:#94a3b8;font-size:0.85rem;">No stops assigned yet.</p>', unsafe_allow_html=True)
    else:
        route_str = " → ".join(
            [f"**{LOCATIONS[s]['icon']} {LOCATIONS[s]['name']}** ({'P' if LOCATIONS[s]['type']=='pickup' else 'D'})"
             for s in stops]
        )
        st.markdown(f"Depot → {route_str} → Depot")

    for v in violations_local:
        st.markdown(f'<div class="warn-box">⚠ {v}</div>', unsafe_allow_html=True)

    if stops and not violations_local:
        st.markdown('<div class="ok-box">✓ Route valid so far</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Scenario
# ═══════════════════════════════════════════════════════════════════════════════
def tab_scenario():
    st.header("Urban Package Delivery — Pickup & Delivery VRP")
    st.markdown(
        "You manage a fleet of delivery vehicles for an urban logistics company. "
        "**5 shipments** must be picked up from their origin and delivered to their destination. "
        "Use **2 vehicles** efficiently — minimise total travel distance while respecting "
        "**capacity** and **precedence** (pickup before delivery) constraints."
    )

    col1, col2 = st.columns([3, 2])

    with col1:
        # Map overview
        empty_routes = {"v1": [], "v2": []}
        fig = draw_map(empty_routes, "v1", highlight_clickable=False)
        fig.update_layout(title="Network Map — All Locations", height=480)
        st.plotly_chart(fig, use_container_width=True, key="scenario_map")

    with col2:
        # Depot info
        st.subheader("Depot")
        st.markdown(
            f'<div class="vrp-card">'
            f'<h4>🏭 {DEPOT["name"]}</h4>'
            f'<p>Starting & ending point for both vehicles<br>'
            f'Coordinates: ({DEPOT["x"]}, {DEPOT["y"]})</p>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Vehicle specs
        st.subheader("Vehicles")
        for vid, veh in VEHICLES.items():
            st.markdown(
                f'<div class="vrp-card route-{vid}">'
                f'<h4 style="color:{veh["color"]}">🚚 {veh["name"]}</h4>'
                f'<p>Capacity: {veh["capacity"]} shipments</p>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # Shipments table
    st.subheader("Shipments")
    rows = []
    for sid, sh in SHIPMENTS.items():
        p = LOCATIONS[sh["pickup"]]
        d = LOCATIONS[sh["delivery"]]
        rows.append({
            "Shipment": sid.upper(),
            "Name": sh["name"],
            "Pickup": f"{p['icon']} {p['name']} ({p['x']}, {p['y']})",
            "Delivery": f"{d['icon']} {d['name']} ({d['x']}, {d['y']})",
            "Demand": sh["demand"],
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Locations table
    st.subheader("All Locations")
    loc_rows = []
    for loc_id, loc in LOCATIONS.items():
        loc_rows.append({
            "ID": loc_id,
            "Icon": loc["icon"],
            "Name": loc["name"],
            "Type": loc["type"].capitalize(),
            "X (km)": loc["x"],
            "Y (km)": loc["y"],
            "Shipment": loc["shipment"].upper(),
        })
    loc_df = pd.DataFrame(loc_rows)
    st.dataframe(loc_df, use_container_width=True, hide_index=True)

    # Rules
    st.subheader("Rules & Constraints")
    st.markdown(
        """
        | Constraint | Description |
        |---|---|
        | **Precedence** | You must visit the pickup location **before** the delivery location for each shipment |
        | **Capacity** | Each vehicle can carry at most **3 shipments** at any time |
        | **Coverage** | Every shipment must be assigned (pickup AND delivery) to exactly one vehicle |
        | **Start/End** | Every vehicle route starts and ends at the **Central Warehouse** |

        **Objective:** Minimise total travel distance (sum of both vehicle routes, including return to depot).

        **Score formula:** `score = min(1000, round(1000 × reference_distance / your_distance))`
        A perfect score of 1000 means you matched the reference (heuristic) solution.
        """
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Plan Routes
# ═══════════════════════════════════════════════════════════════════════════════
def tab_plan():
    st.header("Plan Your Routes")

    # ── Student name ─────────────────────────────────────────────────────────
    name_col, _, reset_col = st.columns([3, 3, 1])
    with name_col:
        student_name = st.text_input(
            "Your name (for leaderboard)",
            value=st.session_state.vrp_student_name,
            placeholder="Enter your name...",
            key="name_input",
        )
        st.session_state.vrp_student_name = student_name

    with reset_col:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Reset All", use_container_width=True):
            st.session_state.vrp_routes = {"v1": [], "v2": []}
            st.session_state.vrp_submitted = False
            st.session_state.vrp_evaluation = None
            st.session_state.vrp_score = 0
            st.rerun()

    if st.session_state.vrp_submitted:
        st.info("✅ You have already submitted a solution. Reset to try again.")
        return

    # ── Active vehicle selector ───────────────────────────────────────────────
    st.markdown("#### Active Vehicle")
    av_col1, av_col2, av_col3 = st.columns([2, 2, 6])
    with av_col1:
        v1_label = "🔵 Vehicle 1 (Blue)"
        v1_active = st.session_state.vrp_active_vehicle == "v1"
        if st.button(
            v1_label,
            use_container_width=True,
            type="primary" if v1_active else "secondary",
            key="btn_v1",
        ):
            st.session_state.vrp_active_vehicle = "v1"
            st.rerun()
    with av_col2:
        v2_label = "🟡 Vehicle 2 (Amber)"
        v2_active = st.session_state.vrp_active_vehicle == "v2"
        if st.button(
            v2_label,
            use_container_width=True,
            type="primary" if v2_active else "secondary",
            key="btn_v2",
        ):
            st.session_state.vrp_active_vehicle = "v2"
            st.rerun()
    with av_col3:
        av = st.session_state.vrp_active_vehicle
        av_color = _C["v1"] if av == "v1" else _C["v2"]
        av_name = VEHICLES[av]["name"]
        st.markdown(
            f'<div class="info-box">Clicking a node on the map will add it to <b style="color:{av_color}">{av_name}</b>\'s route.</div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ── Main layout: map left, controls right ────────────────────────────────
    map_col, ctrl_col = st.columns([3, 2])

    routes = st.session_state.vrp_routes
    active_v = st.session_state.vrp_active_vehicle
    assigned = _assigned_to()

    with map_col:
        fig = draw_map(routes, active_v, highlight_clickable=True)
        event = st.plotly_chart(
            fig,
            use_container_width=True,
            key="plan_map",
            on_select="rerun",
            selection_mode=("points",),
        )

        # ── Handle click ──────────────────────────────────────────────────────
        if event and hasattr(event, "selection") and event.selection:
            sel = event.selection
            points = sel.get("points", [])
            if points:
                pt = points[0]
                cd = pt.get("customdata")
                if cd is not None:
                    loc_id = cd[0] if isinstance(cd, (list, tuple)) else cd

                    if loc_id and loc_id != "depot":
                        loc = LOCATIONS.get(loc_id)
                        if loc:
                            av = st.session_state.vrp_active_vehicle
                            current_route = st.session_state.vrp_routes[av]
                            other_v = "v2" if av == "v1" else "v1"

                            # Already in current vehicle route?
                            if loc_id in current_route:
                                st.warning(f"'{loc['name']}' is already in {VEHICLES[av]['name']}'s route.")
                            # Already in other vehicle route?
                            elif loc_id in st.session_state.vrp_routes[other_v]:
                                st.warning(
                                    f"'{loc['name']}' is already assigned to {VEHICLES[other_v]['name']}. "
                                    "You cannot assign the same stop to two vehicles."
                                )
                            else:
                                # Check precedence for delivery
                                if loc["type"] == "delivery":
                                    sh_id = loc["shipment"]
                                    pickup_id = SHIPMENTS[sh_id]["pickup"]
                                    if pickup_id not in current_route:
                                        st.error(
                                            f"Cannot add delivery '{loc['name']}': "
                                            f"pickup '{LOCATIONS[pickup_id]['name']}' must be added to {VEHICLES[av]['name']} first."
                                        )
                                    else:
                                        st.session_state.vrp_routes[av].append(loc_id)
                                        st.rerun()
                                else:
                                    # Check capacity before adding pickup
                                    cap = VEHICLES[av]["capacity"]
                                    current_pickups = sum(
                                        1 for s in current_route if LOCATIONS[s]["type"] == "pickup"
                                    )
                                    if current_pickups >= cap:
                                        st.error(
                                            f"{VEHICLES[av]['name']} is already at full capacity "
                                            f"({cap} pickups). Cannot add more pickups."
                                        )
                                    else:
                                        st.session_state.vrp_routes[av].append(loc_id)
                                        st.rerun()

        st.caption(
            "Click any node to add it to the active vehicle's route. "
            "Orange circles = pickups, green diamonds = deliveries, dark square = depot."
        )

    with ctrl_col:
        st.markdown("#### Route Details")

        # V1 Panel
        _render_route_panel("v1")
        undo_c1, clr_c1 = st.columns(2)
        with undo_c1:
            if st.button("↩ Undo Last", key="undo_v1", use_container_width=True):
                if st.session_state.vrp_routes["v1"]:
                    st.session_state.vrp_routes["v1"].pop()
                    st.rerun()
        with clr_c1:
            if st.button("🗑 Clear V1", key="clear_v1", use_container_width=True):
                st.session_state.vrp_routes["v1"] = []
                st.rerun()

        st.markdown("")

        # V2 Panel
        _render_route_panel("v2")
        undo_c2, clr_c2 = st.columns(2)
        with undo_c2:
            if st.button("↩ Undo Last", key="undo_v2", use_container_width=True):
                if st.session_state.vrp_routes["v2"]:
                    st.session_state.vrp_routes["v2"].pop()
                    st.rerun()
        with clr_c2:
            if st.button("🗑 Clear V2", key="clear_v2", use_container_width=True):
                st.session_state.vrp_routes["v2"] = []
                st.rerun()

        st.markdown("---")

        # ── Progress & submission ─────────────────────────────────────────────
        all_loc_ids = list(LOCATIONS.keys())
        n_assigned = sum(1 for loc_id in all_loc_ids if loc_id in assigned)
        n_total = len(all_loc_ids)
        progress = n_assigned / n_total if n_total > 0 else 0

        st.markdown("#### Progress")
        st.progress(progress, text=f"{n_assigned}/{n_total} stops assigned")

        # Shipment status
        for sid, sh in SHIPMENTS.items():
            pid = sh["pickup"]
            did = sh["delivery"]
            p_done = pid in assigned
            d_done = did in assigned
            if p_done and d_done:
                pv = assigned[pid]
                dv = assigned[did]
                if pv == dv:
                    vcolor = _C[pv]
                    st.markdown(
                        f'<div class="ok-box">✓ {sh["name"]} ({sid.upper()}) — {VEHICLES[pv]["name"]}</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f'<div class="warn-box">⚠ {sh["name"]} ({sid.upper()}) — split across vehicles!</div>',
                        unsafe_allow_html=True,
                    )
            elif p_done:
                st.markdown(
                    f'<div class="info-box">→ {sh["name"]} ({sid.upper()}) — pickup done, delivery missing</div>',
                    unsafe_allow_html=True,
                )
            elif d_done:
                st.markdown(
                    f'<div class="warn-box">⚠ {sh["name"]} ({sid.upper()}) — delivery done but pickup missing!</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<span style="color:#94a3b8;font-size:0.85rem;">○ {sh["name"]} ({sid.upper()}) — not assigned</span><br>',
                    unsafe_allow_html=True,
                )

        st.markdown("")

        # Ready-to-submit check
        if _all_assigned():
            eval_result = evaluate_solution(routes)
            if eval_result["feasible"]:
                st.markdown('<div class="ok-box"><b>✅ All shipments assigned — Ready to Submit!</b></div>', unsafe_allow_html=True)
                total_d = eval_result["total_distance"]
                st.markdown(f"**Total distance:** {total_d:.2f} km")

                if not student_name.strip():
                    st.warning("Please enter your name before submitting.")
                else:
                    if st.button("🚀 Submit Solution", type="primary", use_container_width=True):
                        ref = get_reference()
                        score = _compute_score(eval_result, ref["total_distance"])
                        st.session_state.vrp_evaluation = eval_result
                        st.session_state.vrp_reference = ref
                        st.session_state.vrp_score = score
                        st.session_state.vrp_submitted = True
                        st.session_state.vrp_student_name = student_name.strip()

                        # Save to leaderboard
                        if _DB_AVAILABLE:
                            try:
                                _db.init_db()
                                _db.save_solution(
                                    student_name.strip(),
                                    eval_result,
                                    ref["total_distance"],
                                    score,
                                )
                            except Exception as e:
                                st.warning(f"Could not save to leaderboard: {e}")
                        else:
                            st.info("Leaderboard not configured (Google Sheets not set up).")

                        st.session_state.vrp_active_tab = 2
                        st.rerun()
            else:
                st.markdown('<div class="warn-box"><b>⚠ All stops assigned but route has violations:</b></div>', unsafe_allow_html=True)
                for v in eval_result["violations"][:5]:
                    st.markdown(f'<div class="warn-box">• {v}</div>', unsafe_allow_html=True)
        else:
            remaining = n_total - n_assigned
            st.markdown(
                f'<div class="info-box">Assign {remaining} more stop(s) to enable submission.</div>',
                unsafe_allow_html=True,
            )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Solution
# ═══════════════════════════════════════════════════════════════════════════════
def tab_solution():
    if not st.session_state.vrp_submitted or st.session_state.vrp_evaluation is None:
        st.info("Complete and submit your routes in the **Plan Routes** tab first.")
        return

    evaluation = st.session_state.vrp_evaluation
    ref = st.session_state.vrp_reference or get_reference()
    score = st.session_state.vrp_score

    st.header("Solution Analysis")
    st.markdown(f"**Student:** {st.session_state.vrp_student_name}")

    # ── Score display ──────────────────────────────────────────────────────────
    sc_col1, sc_col2, sc_col3 = st.columns(3)
    with sc_col1:
        st.metric("Your Score", f"{score} / 1000")
    with sc_col2:
        st.metric("Your Total Distance", f"{evaluation['total_distance']:.2f} km")
    with sc_col3:
        ref_dist = ref["total_distance"]
        gap = round((evaluation["total_distance"] - ref_dist) / ref_dist * 100, 1) if ref_dist else 0
        st.metric("Reference Distance", f"{ref_dist:.2f} km", delta=f"{gap:+.1f}% vs reference")

    if evaluation["feasible"]:
        st.success(f"✅ Feasible solution! Score: {score}/1000")
    else:
        st.error("❌ Infeasible solution — violations detected.")
        for v in evaluation["violations"]:
            st.markdown(f'<div class="warn-box">• {v}</div>', unsafe_allow_html=True)

    st.markdown("---")

    # ── Side-by-side maps ─────────────────────────────────────────────────────
    st.subheader("Route Comparison")
    map_c1, map_c2 = st.columns(2)

    with map_c1:
        st.markdown("**Your Solution**")
        fig_yours = draw_map(st.session_state.vrp_routes, "v1", highlight_clickable=False)
        fig_yours.update_layout(
            title=f"Your Routes — {evaluation['total_distance']:.2f} km total",
            height=420,
        )
        st.plotly_chart(fig_yours, use_container_width=True, key="sol_yours")

    with map_c2:
        st.markdown("**Reference Solution (Heuristic)**")
        fig_ref = draw_map(ref["routes"], "v1", highlight_clickable=False)
        fig_ref.update_layout(
            title=f"Reference Routes — {ref_dist:.2f} km total",
            height=420,
        )
        st.plotly_chart(fig_ref, use_container_width=True, key="sol_ref")

    # ── Detailed route tables ──────────────────────────────────────────────────
    st.subheader("Your Route Details")
    det_c1, det_c2 = st.columns(2)

    for i, (vid, veh) in enumerate(VEHICLES.items()):
        col = det_c1 if i == 0 else det_c2
        with col:
            rr = evaluation["route_results"].get(vid, {})
            stops = rr.get("stops", [])
            d = rr.get("distance", 0.0)

            st.markdown(
                f'<div class="vrp-card route-{vid}">'
                f'<h4 style="color:{veh["color"]}">🚚 {veh["name"]}</h4>'
                f'<p>Distance: {d:.2f} km | Stops: {len(stops)}</p>'
                f'</div>',
                unsafe_allow_html=True,
            )

            if stops:
                route_rows = []
                load = 0
                for j, sid in enumerate(stops, 1):
                    loc = LOCATIONS[sid]
                    sh = SHIPMENTS[loc["shipment"]]
                    if loc["type"] == "pickup":
                        load += sh["demand"]
                        action = "Pick up"
                    else:
                        action = "Deliver"
                        load -= sh["demand"]
                    route_rows.append({
                        "Step": j,
                        "Action": action,
                        "Location": f"{loc['icon']} {loc['name']}",
                        "Shipment": sh["name"],
                        "Load After": load,
                    })
                st.dataframe(pd.DataFrame(route_rows), use_container_width=True, hide_index=True)
            else:
                st.markdown("*No stops*")

    # ── Reference route details ─────────────────────────────────────────────
    st.subheader("Reference Route Details")
    ref_c1, ref_c2 = st.columns(2)

    for i, (vid, veh) in enumerate(VEHICLES.items()):
        col = ref_c1 if i == 0 else ref_c2
        with col:
            ref_stops = ref["routes"].get(vid, []) if ref["routes"] else []
            ref_d = route_distance(ref_stops)

            st.markdown(
                f'<div class="vrp-card route-{vid}">'
                f'<h4 style="color:{veh["color"]}">🚚 {veh["name"]} (Reference)</h4>'
                f'<p>Distance: {ref_d:.2f} km | Stops: {len(ref_stops)}</p>'
                f'</div>',
                unsafe_allow_html=True,
            )

            if ref_stops:
                ref_rows = []
                load = 0
                for j, sid in enumerate(ref_stops, 1):
                    loc = LOCATIONS[sid]
                    sh = SHIPMENTS[loc["shipment"]]
                    if loc["type"] == "pickup":
                        load += sh["demand"]
                        action = "Pick up"
                    else:
                        action = "Deliver"
                        load -= sh["demand"]
                    ref_rows.append({
                        "Step": j,
                        "Action": action,
                        "Location": f"{loc['icon']} {loc['name']}",
                        "Shipment": sh["name"],
                        "Load After": load,
                    })
                st.dataframe(pd.DataFrame(ref_rows), use_container_width=True, hide_index=True)
            else:
                st.markdown("*No stops*")

    # ── Learning reflection ────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Learning Reflection")
    st.markdown(
        """
        **Key VRP concepts demonstrated:**

        - **Routing:** The order of stops matters — a bad sequence can waste many kilometres.
        - **Capacity constraint:** Vehicles can't carry unlimited cargo. When a vehicle is full, it may need to deliver before picking up more.
        - **Precedence constraint:** You cannot deliver something you haven't picked up yet. This restricts which stop sequences are feasible.
        - **Optimisation:** With 5 shipments and 2 vehicles, there are many possible route combinations. The reference solver enumerates all shipment-to-vehicle assignments and applies a nearest-neighbour heuristic to find a good (but not necessarily optimal) solution.
        - **Trade-off:** Splitting shipments evenly between vehicles isn't always best — sometimes assigning more stops to one vehicle reduces total travel if clusters exist.
        """
    )

    if st.button("🔄 Play Again", type="secondary"):
        st.session_state.vrp_routes = {"v1": [], "v2": []}
        st.session_state.vrp_submitted = False
        st.session_state.vrp_evaluation = None
        st.session_state.vrp_score = 0
        st.session_state.vrp_active_tab = 1
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Leaderboard
# ═══════════════════════════════════════════════════════════════════════════════
def tab_leaderboard():
    st.header("Leaderboard — Top Feasible Solutions")

    if not _DB_AVAILABLE:
        st.warning(
            "Leaderboard is not available: Google Sheets credentials are not configured. "
            "To enable the leaderboard, add `.streamlit/secrets.toml` with `gcp_json` and `[sheet]` settings."
        )
        return

    try:
        _db.init_db()
    except Exception as e:
        st.error(f"Failed to initialise leaderboard: {e}")
        return

    col_refresh, _ = st.columns([1, 5])
    with col_refresh:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()

    try:
        data = _db.get_leaderboard(top_n=50)
    except Exception as e:
        st.error(f"Failed to load leaderboard: {e}")
        return

    if not data:
        st.info("No feasible solutions submitted yet. Be the first!")
        return

    # Medals for top 3
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}

    rows = []
    for entry in data:
        rank = entry["rank"]
        medal = medals.get(rank, str(rank))
        rows.append({
            "Rank": medal,
            "Name": entry["student_name"],
            "Score": int(entry["score"]),
            "Distance (km)": round(entry["total_distance"], 2),
            "Ref. Distance": round(entry["reference_distance"], 2),
            "Gap (%)": f"{entry['gap_pct']:+.1f}%",
            "Plays": entry["plays"],
            "Best At": entry["best_at"],
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True, height=600)

    # Highlight current student if submitted
    if st.session_state.vrp_submitted and st.session_state.vrp_student_name:
        name = st.session_state.vrp_student_name.strip().lower()
        for entry in data:
            if entry["student_name"].strip().lower() == name:
                st.success(
                    f"Your best score: **{int(entry['score'])}** (Rank #{entry['rank']}) — "
                    f"{entry['total_distance']:.2f} km"
                )
                break


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    st.title("🚚 Pickup & Delivery VRP Game — IE105000")
    st.markdown(
        "Plan efficient vehicle routes for urban package delivery. "
        "Apply **Operations Research** concepts: routing, capacity, precedence, and optimisation."
    )

    # Active tab index control (for auto-navigation after submit)
    active_tab_idx = st.session_state.get("vrp_active_tab", 0)

    tab_labels = ["📦 Scenario", "🚚 Plan Routes", "📊 Solution", "🏆 Leaderboard"]
    tabs = st.tabs(tab_labels)

    with tabs[0]:
        tab_scenario()

    with tabs[1]:
        # Reset auto-navigation flag when user is on Plan tab
        tab_plan()

    with tabs[2]:
        tab_solution()

    with tabs[3]:
        tab_leaderboard()

    # Auto-navigate to solution tab after submit via JavaScript
    if st.session_state.get("vrp_active_tab") == 2 and st.session_state.vrp_submitted:
        st.session_state.vrp_active_tab = 0  # reset so it doesn't keep switching
        # Streamlit doesn't support programmatic tab switching directly,
        # but show a prominent banner pointing to the Solution tab
        st.toast("✅ Solution submitted! Check the 📊 Solution tab.", icon="🚚")


if __name__ == "__main__" or True:
    main()
