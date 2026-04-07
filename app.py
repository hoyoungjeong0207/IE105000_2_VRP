"""app.py — Streamlit UI for the IE105000 VRP Pickup & Delivery Game."""
import math
import random

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


from engine import check_route, evaluate_solution, route_distance, dist, get_loc
from scenario import (
    DEPOT, LOCATION_POOL, PAIR_COLORS, VEHICLE_COLORS,
    DEFAULT_NUM_VEHICLES, DEFAULT_NUM_SHIPMENTS, generate_scenario,
)
from solver import solve

try:
    import db as _db
    _DB_AVAILABLE = True
except Exception:
    _DB_AVAILABLE = False

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="VRP Pickup & Delivery — IE105000",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Color palette ──────────────────────────────────────────────────────────────
_C = {
    "bg":      "#0f172a",
    "surface": "#1e293b",
    "border":  "#334155",
    "text":    "#f1f5f9",
    "muted":   "#94a3b8",
    "depot":   "#93c5fd",
    "grid":    "#1e293b",
    "warn":    "#f87171",
    "ok":      "#4ade80",
    "info":    "#60a5fa",
}

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.vrp-card {
    background: #1e293b; border: 1px solid #334155;
    border-radius: 8px; padding: 0.9rem 1.1rem; margin-bottom: 0.6rem;
}
.vrp-card h4 { margin: 0 0 0.3rem 0; font-size: 0.95rem; color: #f1f5f9; }
.vrp-card p  { margin: 0; font-size: 0.82rem; color: #94a3b8; }
.warn-box { background:#1f0f0f; border:1px solid #f87171; border-radius:6px;
    padding:0.5rem 0.8rem; margin:0.3rem 0; font-size:0.85rem; color:#fca5a5; }
.ok-box   { background:#0f1f0f; border:1px solid #4ade80; border-radius:6px;
    padding:0.5rem 0.8rem; margin:0.3rem 0; font-size:0.85rem; color:#86efac; }
.info-box { background:#0f172a; border:1px solid #60a5fa; border-radius:6px;
    padding:0.5rem 0.8rem; margin:0.3rem 0; font-size:0.85rem; color:#93c5fd; }
.score-big { font-size:2.5rem; font-weight:700; text-align:center; color:#f1f5f9; }
.pair-legend { display:flex; flex-wrap:wrap; gap:0.4rem 1rem;
    font-size:0.78rem; color:#94a3b8; margin:0.3rem 0 0.6rem 0; }

/* ── Mobile: stack all Streamlit columns ── */
@media (max-width: 768px) {
    [data-testid="stHorizontalBlock"] {
        flex-direction: column !important;
        gap: 0.3rem !important;
    }
    [data-testid="stColumn"] {
        width: 100% !important;
        flex: 1 1 100% !important;
        min-width: 100% !important;
    }
    /* Bigger tap targets for buttons */
    .stButton > button {
        min-height: 2.8rem !important;
        font-size: 0.95rem !important;
    }
    /* Smaller title on mobile */
    h1 { font-size: 1.4rem !important; }
    h2 { font-size: 1.2rem !important; }
    h3 { font-size: 1.05rem !important; }
    /* Reduce plotly chart padding */
    [data-testid="stPlotlyChart"] { padding: 0 !important; }
}
</style>
""", unsafe_allow_html=True)


# ── Session state init ─────────────────────────────────────────────────────────
def _init_state():
    defaults = {
        "vrp_game_started":   False,
        "vrp_num_vehicles":   DEFAULT_NUM_VEHICLES,
        "vrp_num_shipments":  DEFAULT_NUM_SHIPMENTS,
        "vrp_seed":           None,
        "vrp_locations":      {},
        "vrp_shipments":      {},
        "vrp_vehicles":       {},
        "vrp_routes":         {},
        "vrp_active_vehicle": "v1",
        "vrp_submitted":      False,
        "vrp_evaluation":     None,
        "vrp_optimal":        None,
        "vrp_score":          0,
        "vrp_student_name":   "",
        "vrp_student_id":     "",
        "vrp_goto_solution":  False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()


# ── Scenario helpers ───────────────────────────────────────────────────────────
def _sc():
    """Return (locations, shipments, vehicles) from session state."""
    return (
        st.session_state.vrp_locations,
        st.session_state.vrp_shipments,
        st.session_state.vrp_vehicles,
    )


@st.cache_data
def _cached_solve(seed, num_vehicles, num_shipments):
    locs, ships, vehs = generate_scenario(num_vehicles, num_shipments, seed)
    return solve(locs, ships, vehs)


def _assigned_to():
    result = {}
    for vid, stops in st.session_state.vrp_routes.items():
        for s in stops:
            result[s] = vid
    return result


def _all_assigned():
    locations = st.session_state.vrp_locations
    assigned = _assigned_to()
    return all(loc_id in assigned for loc_id in locations)


def _compute_score(student_dist, optimal_dist):
    if student_dist == 0 or optimal_dist == 0:
        return 0
    return min(1000, round(1000 * optimal_dist / student_dist))


def pair_color(pair_num):
    return PAIR_COLORS[(pair_num - 1) % len(PAIR_COLORS)]


# ── Map drawing ────────────────────────────────────────────────────────────────
def draw_map(routes, active_vehicle, locations, shipments, vehicles, highlight_clickable=True):
    fig = go.Figure()

    assigned = {}
    for vid, stops in routes.items():
        for s in stops:
            assigned[s] = vid

    # 1. Legend entries for node shapes
    fig.add_trace(go.Scatter(
        x=[None], y=[None], mode="markers",
        marker=dict(symbol="circle", size=12, color="#94a3b8"),
        name="● Pickup",
        showlegend=True, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=[None], y=[None], mode="markers",
        marker=dict(symbol="diamond", size=12, color="#94a3b8"),
        name="◆ Delivery",
        showlegend=True, hoverinfo="skip",
    ))

    # 2. Route lines per vehicle
    for vid, stop_ids in routes.items():
        if not stop_ids:
            continue
        veh = vehicles[vid]
        full_route = ["depot"] + list(stop_ids) + ["depot"]
        xs, ys = [], []
        for loc_id in full_route:
            loc = DEPOT if loc_id == "depot" else locations[loc_id]
            xs.append(loc["x"])
            ys.append(loc["y"])
        d_val = route_distance(stop_ids, locations)
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines+markers",
            line=dict(color=veh["color"], width=3),
            marker=dict(symbol="arrow", size=10, color=veh["color"], angleref="previous"),
            name=f"{veh['name']} ({d_val:.2f} km)",
            showlegend=True, hoverinfo="skip",
        ))

    # 3. Location nodes — one trace per location for click detection
    for loc_id, loc in locations.items():
        sh = shipments[loc["shipment"]]
        pnum = loc["pair_num"]
        color = pair_color(pnum)
        symbol = "circle" if loc["type"] == "pickup" else "diamond"
        label = f"{pnum}{'P' if loc['type'] == 'pickup' else 'D'}"

        if loc_id in assigned:
            vid = assigned[loc_id]
            border_color = vehicles[vid]["color"]
            border_width = 3
        elif highlight_clickable:
            border_color = color
            border_width = 2
        else:
            border_color = "#0f172a"
            border_width = 1

        hover = (
            f"<b>{label}</b><br>"
            f"{'Pickup' if loc['type'] == 'pickup' else 'Delivery'} — Shipment {pnum}<br>"
            f"Coords: ({loc['x']}, {loc['y']})"
            + (f"<br>→ {vehicles[assigned[loc_id]]['name']}" if loc_id in assigned else "")
        )

        fig.add_trace(go.Scatter(
            x=[loc["x"]], y=[loc["y"]],
            mode="markers+text",
            marker=dict(
                symbol=symbol, size=20,
                color=color, opacity=0.95,
                line=dict(color=border_color, width=border_width),
            ),
            text=[label],
            textposition="middle center",
            textfont=dict(size=10, color="white", family="monospace"),
            customdata=[[loc_id]],
            hovertext=[hover], hoverinfo="text",
            showlegend=False,
        ))

    # 4. Depot
    fig.add_trace(go.Scatter(
        x=[DEPOT["x"]], y=[DEPOT["y"]],
        mode="markers+text",
        marker=dict(symbol="square", size=22, color="#1e3a5f", line=dict(color=_C["depot"], width=2)),
        text=["🏭"],
        textposition="middle center",
        customdata=[["depot"]],
        hovertext=[f"<b>🏭 {DEPOT['name']}</b><br>Start/end for all vehicles"],
        hoverinfo="text",
        name="Depot", showlegend=True,
    ))

    # 5. Annotations: location name labels
    annotations = [dict(
        x=DEPOT["x"], y=DEPOT["y"] - 0.6,
        text=f"<b>{DEPOT['name']}</b>",
        showarrow=False,
        font=dict(size=10, color=_C["depot"]),
        bgcolor="rgba(15,23,42,0.85)", borderpad=2,
    )]
    for loc_id, loc in locations.items():
        dy = 0.65 if loc["y"] < 5 else -0.65
        dx = 0.3 if loc["x"] < 1.5 else (-0.3 if loc["x"] > 8.5 else 0)
        pnum = loc["pair_num"]
        color = pair_color(pnum)
        tag = "P" if loc["type"] == "pickup" else "D"
        annotations.append(dict(
            x=loc["x"] + dx, y=loc["y"] + dy,
            text=f"<b>{pnum}{tag}</b>",
            showarrow=False,
            font=dict(size=9, color=color),
            bgcolor="rgba(15,23,42,0.85)", borderpad=2,
        ))

    fig.update_layout(
        annotations=annotations,
        plot_bgcolor=_C["bg"],
        paper_bgcolor=_C["bg"],
        xaxis=dict(range=[-0.3, 10.7], gridcolor=_C["grid"], gridwidth=1, dtick=1,
                   title=dict(text="x (km)", font=dict(color=_C["muted"])),
                   tickfont=dict(color=_C["muted"]), showline=True,
                   linecolor=_C["border"], zeroline=False),
        yaxis=dict(range=[-0.3, 10.7], gridcolor=_C["grid"], gridwidth=1, dtick=1,
                   title=dict(text="y (km)", font=dict(color=_C["muted"])),
                   tickfont=dict(color=_C["muted"]), showline=True,
                   linecolor=_C["border"], zeroline=False,
                   scaleanchor="x", scaleratio=1),
        legend=dict(orientation="v", x=1.01, y=1,
                    bgcolor="rgba(15,23,42,0.9)", bordercolor=_C["border"],
                    borderwidth=1, font=dict(size=10, color=_C["text"])),
        margin=dict(l=40, r=160, t=20, b=40),
        height=540,
        clickmode="event+select",
        dragmode=False,
        hovermode="closest",
        font=dict(color=_C["text"]),
    )
    return fig


# ── Route panel ────────────────────────────────────────────────────────────────
def _render_route_panel(vehicle_id):
    locations, shipments, vehicles = _sc()
    veh = vehicles[vehicle_id]
    stops = st.session_state.vrp_routes.get(vehicle_id, [])
    color = veh["color"]
    cap = veh["capacity"]

    load = 0
    picked = set()
    violations_local = []
    for sid in stops:
        loc = locations[sid]
        sh_id = loc["shipment"]
        if loc["type"] == "pickup":
            load += 1
            picked.add(sh_id)
            if load > cap:
                violations_local.append(f"Over capacity at {loc['pair_num']}P")
        else:
            if sh_id not in picked:
                violations_local.append(f"Delivery before pickup: {loc['pair_num']}D")
            else:
                load -= 1

    d_val = route_distance(stops, locations) if stops else 0.0

    st.markdown(
        f'<div class="vrp-card" style="border-left:4px solid {color}">'
        f'<h4 style="color:{color}">🚚 {veh["name"]}</h4>'
        f'<p>Shipments: {len([s for s in stops if locations[s]["type"] == "pickup"])}/{cap} &nbsp;|&nbsp; '
        f'Distance: {d_val:.2f} km</p>'
        f'</div>', unsafe_allow_html=True,
    )

    if not stops:
        st.markdown('<p style="color:#94a3b8;font-size:0.82rem;margin:0">No stops yet.</p>', unsafe_allow_html=True)
    else:
        parts = []
        for s in stops:
            loc = locations[s]
            pnum = loc["pair_num"]
            tag = "P" if loc["type"] == "pickup" else "D"
            c = pair_color(pnum)
            parts.append(f'<span style="color:{c};font-weight:bold">{pnum}{tag}</span>')
        st.markdown(
            f'<p style="font-size:0.85rem;color:#f1f5f9">Depot → {" → ".join(parts)} → Depot</p>',
            unsafe_allow_html=True,
        )

    for v in violations_local:
        st.markdown(f'<div class="warn-box">⚠ {v}</div>', unsafe_allow_html=True)
    if stops and not violations_local:
        st.markdown('<div class="ok-box">✓ Valid so far</div>', unsafe_allow_html=True)


def _start_game(num_vehicles, num_shipments):
    seed = random.randint(0, 99999)
    locations, shipments, vehicles = generate_scenario(num_vehicles, num_shipments, seed)
    st.session_state.vrp_num_vehicles   = num_vehicles
    st.session_state.vrp_num_shipments  = num_shipments
    st.session_state.vrp_seed           = seed
    st.session_state.vrp_locations      = locations
    st.session_state.vrp_shipments      = shipments
    st.session_state.vrp_vehicles       = vehicles
    st.session_state.vrp_routes         = {vid: [] for vid in vehicles}
    st.session_state.vrp_active_vehicle = list(vehicles.keys())[0]
    st.session_state.vrp_submitted      = False
    st.session_state.vrp_evaluation     = None
    st.session_state.vrp_optimal        = None
    st.session_state.vrp_score          = 0
    st.session_state.vrp_game_started   = True


# ══════════════════════════════════════════════════════════════════════════════
# GAME TABS
# ══════════════════════════════════════════════════════════════════════════════


def tab_plan():
    # ── Game settings panel (always visible at top) ──────────────────────────
    with st.expander("⚙️ Game Settings", expanded=not st.session_state.vrp_game_started):
        s_col1, s_col2, s_col3 = st.columns([2, 2, 1])
        with s_col1:
            num_vehicles = st.slider("Vehicles", 1, 3, st.session_state.vrp_num_vehicles, key="cfg_vehicles")
        with s_col2:
            num_shipments = st.slider("Shipments", 2, 6, st.session_state.vrp_num_shipments, key="cfg_shipments")
        with s_col3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🚀 Start", type="primary", use_container_width=True, key="cfg_start"):
                _start_game(num_vehicles, num_shipments)
                st.rerun()

    if not st.session_state.vrp_game_started:
        st.info("Configure your game above and press **Start**.")
        return

    locations, shipments, vehicles = _sc()
    vehicle_ids = list(vehicles.keys())

    # ── Reset button ─────────────────────────────────────────────────────────
    _, rc = st.columns([5, 1])
    with rc:
        if st.button("🔄 Reset Routes", use_container_width=True):
            st.session_state.vrp_routes    = {vid: [] for vid in vehicles}
            st.session_state.vrp_submitted = False
            st.session_state.vrp_evaluation = None
            st.session_state.vrp_score = 0
            st.rerun()

    if st.session_state.vrp_submitted:
        st.info("✅ Already submitted. Reset routes or start a new game to try again.")
        return

    # ── Vehicle selector buttons ─────────────────────────────────────────────
    st.markdown("#### Select Active Vehicle")
    veh_cols = st.columns(len(vehicle_ids) + 1)
    for i, vid in enumerate(vehicle_ids):
        veh = vehicles[vid]
        is_active = st.session_state.vrp_active_vehicle == vid
        with veh_cols[i]:
            label = f"🚚 {veh['name']}"
            if st.button(label, key=f"btn_{vid}", use_container_width=True,
                         type="primary" if is_active else "secondary"):
                st.session_state.vrp_active_vehicle = vid
                st.rerun()
    with veh_cols[-1]:
        av = st.session_state.vrp_active_vehicle
        av_color = vehicles[av]["color"]
        av_name = vehicles[av]["name"]
        st.markdown(
            f'<div class="info-box" style="margin-top:0.3rem">Clicking map → adds to '
            f'<b style="color:{av_color}">{av_name}</b></div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    routes   = st.session_state.vrp_routes
    active_v = st.session_state.vrp_active_vehicle
    assigned = _assigned_to()

    # ── Map (full width) ─────────────────────────────────────────────────────
    fig = draw_map(routes, active_v, locations, shipments, vehicles, highlight_clickable=True)
    fig.update_layout(height=420, margin=dict(l=30, r=30, t=10, b=30))

    # Pair legend
    items = "".join(
        f'<span style="color:{pair_color(sh["pair_num"])};font-weight:bold;white-space:nowrap">'
        f'{sh["pair_num"]}P → {sh["pair_num"]}D'
        f'</span>'
        for sh in shipments.values()
    )
    st.markdown(f'<div class="pair-legend">{items}</div>', unsafe_allow_html=True)

    event = st.plotly_chart(
        fig, use_container_width=True, key="plan_map",
        on_select="rerun", selection_mode=("points",),
        config={"displayModeBar": False},
    )
    st.caption("Tap a node to add it to the active vehicle's route.")

    # Handle click
    if event and hasattr(event, "selection") and event.selection:
        points = event.selection.get("points", [])
        if points:
            cd = points[0].get("customdata")
            loc_id = (cd[0] if isinstance(cd, (list, tuple)) else cd) if cd is not None else None
            if loc_id and loc_id != "depot":
                loc = locations.get(loc_id)
                if loc:
                    av = st.session_state.vrp_active_vehicle
                    cur_route = st.session_state.vrp_routes[av]
                    other_vs = [v for v in vehicle_ids if v != av]
                    in_other = any(loc_id in st.session_state.vrp_routes[v] for v in other_vs)

                    if loc_id in cur_route:
                        st.warning(f"Already in {vehicles[av]['name']}'s route.")
                    elif in_other:
                        st.warning("Already assigned to another vehicle.")
                    elif loc["type"] == "delivery":
                        pid = shipments[loc["shipment"]]["pickup"]
                        if pid not in cur_route:
                            pnum = locations[pid]["pair_num"]
                            st.error(f"Pick up {pnum}P first.")
                        else:
                            st.session_state.vrp_routes[av].append(loc_id)
                            st.rerun()
                    else:
                        pickups_in = sum(1 for s in cur_route if locations[s]["type"] == "pickup")
                        if pickups_in >= vehicles[av]["capacity"]:
                            st.error(f"{vehicles[av]['name']} at capacity.")
                        else:
                            st.session_state.vrp_routes[av].append(loc_id)
                            st.rerun()

    st.markdown("---")

    # ── Route details (below map, stacks on mobile) ───────────────────────────
    all_loc_ids = list(locations.keys())
    n_assigned  = sum(1 for l in all_loc_ids if l in assigned)
    n_total     = len(all_loc_ids)
    st.progress(n_assigned / n_total if n_total else 0, text=f"{n_assigned}/{n_total} stops assigned")

    # Per-vehicle panels in columns (stack on mobile via CSS)
    veh_panel_cols = st.columns(len(vehicle_ids))
    for i, vid in enumerate(vehicle_ids):
        with veh_panel_cols[i]:
            _render_route_panel(vid)
            u_col, c_col = st.columns(2)
            with u_col:
                if st.button("↩ Undo", key=f"undo_{vid}", use_container_width=True):
                    if st.session_state.vrp_routes[vid]:
                        st.session_state.vrp_routes[vid].pop()
                        st.rerun()
            with c_col:
                if st.button(f"🗑 Clear", key=f"clear_{vid}", use_container_width=True):
                    st.session_state.vrp_routes[vid] = []
                    st.rerun()

    st.markdown("---")

    # Shipment checklist
    for sid, sh in shipments.items():
        pid, did = sh["pickup"], sh["delivery"]
        p_done = pid in assigned
        d_done = did in assigned
        pnum   = sh["pair_num"]
        c      = pair_color(pnum)
        p_veh  = assigned.get(pid, "")
        d_veh  = assigned.get(did, "")

        if p_done and d_done and p_veh == d_veh:
            st.markdown(f'<div class="ok-box">✓ <b style="color:{c}">Shipment {pnum}</b> — {vehicles[p_veh]["name"]}</div>', unsafe_allow_html=True)
        elif p_done and d_done and p_veh != d_veh:
            st.markdown(f'<div class="warn-box">⚠ Shipment {pnum} split across vehicles!</div>', unsafe_allow_html=True)
        elif p_done:
            st.markdown(f'<div class="info-box"><b style="color:{c}">Shipment {pnum}</b>: pickup ✓, delivery missing</div>', unsafe_allow_html=True)
        elif d_done:
            st.markdown(f'<div class="warn-box">⚠ Shipment {pnum}: delivery added, pickup missing!</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<p style="color:#94a3b8;font-size:0.85rem;margin:2px 0">○ <b style="color:{c}">Shipment {pnum}</b>: not assigned</p>', unsafe_allow_html=True)

    st.markdown("")

    # Submit
    if _all_assigned():
        eval_result = evaluate_solution(routes, locations, shipments, vehicles)
        if eval_result["feasible"]:
            st.markdown('<div class="ok-box"><b>✅ All assigned — Ready to Submit!</b></div>', unsafe_allow_html=True)
            st.markdown(f"**Total distance:** {eval_result['total_distance']:.2f} km")
            sc1, sc2 = st.columns(2)
            with sc1:
                submit_name = st.text_input("Your Name", value=st.session_state.vrp_student_name,
                                            placeholder="홍길동", key="submit_name")
            with sc2:
                submit_id = st.text_input("Student ID", value=st.session_state.vrp_student_id,
                                          placeholder="2024XXXXXX", key="submit_id")
            if not submit_name.strip():
                st.warning("이름을 입력해주세요.")
            else:
                if st.button("🚀 Submit", type="primary", use_container_width=True):
                    st.session_state.vrp_student_name = submit_name.strip()
                    st.session_state.vrp_student_id   = submit_id.strip()
                    seed = st.session_state.vrp_seed
                    n_v  = st.session_state.vrp_num_vehicles
                    n_s  = st.session_state.vrp_num_shipments
                    optimal = _cached_solve(seed, n_v, n_s)
                    score   = _compute_score(eval_result["total_distance"], optimal["total_distance"])
                    st.session_state.vrp_evaluation = eval_result
                    st.session_state.vrp_optimal    = optimal
                    st.session_state.vrp_score      = score
                    st.session_state.vrp_submitted       = True
                    st.session_state.vrp_goto_solution   = True
                    if _DB_AVAILABLE:
                        try:
                            _db.init_db()
                            _db.save_solution(
                                submit_name.strip(), eval_result,
                                optimal["total_distance"], score,
                                student_id=submit_id.strip(),
                                seed=seed, num_vehicles=n_v, num_shipments=n_s,
                            )
                        except Exception as e:
                            st.warning(f"리더보드 저장 실패: {e}")
                    st.rerun()
        else:
            st.markdown('<div class="warn-box"><b>⚠ Violations detected:</b></div>', unsafe_allow_html=True)
            for v in eval_result["violations"][:5]:
                st.markdown(f'<div class="warn-box">• {v}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="info-box">{n_total - n_assigned} more stop(s) to assign.</div>', unsafe_allow_html=True)


def tab_solution():
    if not st.session_state.vrp_submitted or st.session_state.vrp_evaluation is None:
        st.info("Submit your routes in the **Plan Routes** tab first.")
        return

    locations, shipments, vehicles = _sc()
    evaluation = st.session_state.vrp_evaluation
    optimal    = st.session_state.vrp_optimal
    score      = st.session_state.vrp_score

    st.header("Solution Analysis")
    st.markdown(f"**Student:** {st.session_state.vrp_student_name}")

    opt_dist  = optimal["total_distance"]
    your_dist = evaluation["total_distance"]
    gap_pct   = (your_dist - opt_dist) / opt_dist * 100 if opt_dist else 0

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Your Score", f"{score} / 1000")
    with c2:
        st.metric("Your Distance", f"{your_dist:.2f} km")
    with c3:
        st.metric("Optimal Distance", f"{opt_dist:.2f} km", delta=f"{gap_pct:+.1f}% gap")

    if evaluation["feasible"]:
        st.success(f"✅ Feasible! Score: {score}/1000 — Optimality gap: {gap_pct:.1f}%")
    else:
        st.error("❌ Infeasible solution.")
        for v in evaluation["violations"]:
            st.markdown(f'<div class="warn-box">• {v}</div>', unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("Route Comparison")
    mc1, mc2 = st.columns(2)
    with mc1:
        st.markdown("**Your Solution**")
        fig_y = draw_map(
            st.session_state.vrp_routes, list(vehicles.keys())[0],
            locations, shipments, vehicles, highlight_clickable=False,
        )
        fig_y.update_layout(title=f"Your Routes — {your_dist:.2f} km", height=400)
        st.plotly_chart(fig_y, use_container_width=True, key="sol_yours", config={"displayModeBar": False})
    with mc2:
        st.markdown("**Optimal Solution**")
        fig_o = draw_map(
            optimal["routes"], list(vehicles.keys())[0],
            locations, shipments, vehicles, highlight_clickable=False,
        )
        fig_o.update_layout(title=f"Optimal Routes — {opt_dist:.2f} km", height=400)
        st.plotly_chart(fig_o, use_container_width=True, key="sol_optimal", config={"displayModeBar": False})

    st.subheader("Route Details")
    rc1, rc2 = st.columns(2)
    for i, (vid, veh) in enumerate(vehicles.items()):
        col = rc1 if i % 2 == 0 else rc2
        with col:
            rr = evaluation["route_results"].get(vid, {})
            stops = rr.get("stops", [])
            d = rr.get("distance", 0.0)
            st.markdown(
                f'<div class="vrp-card" style="border-left:4px solid {veh["color"]}">'
                f'<h4 style="color:{veh["color"]}">🚚 {veh["name"]}</h4>'
                f'<p>Distance: {d:.2f} km | Stops: {len(stops)}</p></div>',
                unsafe_allow_html=True,
            )
            if stops:
                rows = []
                load = 0
                for j, sid in enumerate(stops, 1):
                    loc = locations[sid]
                    sh  = shipments[loc["shipment"]]
                    if loc["type"] == "pickup":
                        load += 1
                        action = "Pick up"
                    else:
                        action = "Deliver"
                        load -= 1
                    rows.append({
                        "Step": j,
                        "Stop": f"{sh['pair_num']}{'P' if loc['type'] == 'pickup' else 'D'}",
                        "Action": action,
                        "Load": load,
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("Learning Points")
    st.markdown(f"""
- **Optimality gap of {gap_pct:.1f}%** means your solution travels {gap_pct:.1f}% more than the mathematical optimum.
- **Precedence constraint**: You must pick up before delivering — this restricts valid route sequences.
- **Capacity constraint**: Vehicles have limited load — sometimes you must deliver before picking up more.
- **Clustering**: Grouping geographically nearby pickups/deliveries to the same vehicle reduces travel.
- **Exact optimum**: For this small problem, the computer checked all feasible route combinations to find the true minimum distance of {opt_dist:.2f} km.
""")

    if st.button("🔄 New Game", type="secondary"):
        st.session_state.vrp_game_started = False
        st.rerun()


def tab_leaderboard():
    st.header("🏆 Leaderboard")
    if not _DB_AVAILABLE:
        st.warning("Leaderboard not configured (Google Sheets not set up).")
        return
    try:
        data = _db.get_leaderboard(top_n=50)
    except Exception as e:
        st.error(f"Failed to load leaderboard: {e}")
        return

    if st.button("🔄 Refresh"):
        if _DB_AVAILABLE:
            _db.get_leaderboard.clear()
        st.rerun()

    if not data:
        st.info("No submissions yet. Be the first!")
        return

    st.caption("동점 시 고객 수(Shipments) 많은 순 → 차량 수(Vehicles) 많은 순으로 정렬")

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    rows = []
    for entry in data:
        rank = entry["rank"]
        rows.append({
            "Rank": medals.get(rank, str(rank)),
            "Name": entry["student_name"],
            "Score": int(entry["score"]),
            "Shipments": entry["num_shipments"],
            "Vehicles": entry["num_vehicles"],
            "Distance (km)": round(entry["total_distance"], 2),
            "Gap": f"{entry['gap_pct']:+.1f}%",
            "Plays": entry["plays"],
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=500)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main():
    st.title("🚚 Pickup & Delivery VRP Game — IE105000")

    # Auto-switch to Solution tab after submit
    if st.session_state.get("vrp_goto_solution"):
        st.session_state.vrp_goto_solution = False
        st.components.v1.html("""
        <script>
            setTimeout(function() {
                var tabs = window.parent.document.querySelectorAll('[data-baseweb="tab"]');
                if (tabs.length >= 2) tabs[1].click();
            }, 100);
        </script>
        """, height=0)

    tabs = st.tabs(["🚚 Plan Routes", "📊 Solution", "🏆 Leaderboard"])
    with tabs[0]: tab_plan()
    with tabs[1]: tab_solution()
    with tabs[2]: tab_leaderboard()


if __name__ == "__main__" or True:
    main()
