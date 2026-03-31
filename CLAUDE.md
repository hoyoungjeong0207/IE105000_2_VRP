# CLAUDE.md — IE105000 VRP Pickup & Delivery Game

## What This Is

An interactive Pickup & Delivery Vehicle Routing Problem (PD-VRP) learning game
deployed on Streamlit Cloud. Students plan delivery routes for an urban logistics
scenario, learning core Operations Research concepts: routing, capacity constraints,
precedence constraints, and combinatorial optimisation.

Course: IE105000 (Operations Research / Logistics)

---

## Scenario Parameters

### Network
- Grid: 10 × 10 km urban area
- Depot: Central Warehouse at (5.0, 5.0)

### Vehicles
| ID | Name      | Capacity | Color  |
|----|-----------|----------|--------|
| v1 | Vehicle 1 | 3 units  | Blue   |
| v2 | Vehicle 2 | 3 units  | Amber  |

### Shipments (5 total, demand = 1 each)
| ID | Name          | Pickup Location      | Delivery Location   |
|----|---------------|----------------------|---------------------|
| s1 | Fresh Bread   | Bakery (1, 8)        | Office Tower (9, 9) |
| s2 | Lab Equipment | Electronics (8, 2)   | University Lab (2, 1) |
| s3 | Flowers       | Flower Market (1, 3) | Hospital (8, 6)     |
| s4 | Documents     | Print Shop (9, 7)    | School (3, 2)       |
| s5 | Café Supplies | Café Supply (4, 9)   | Restaurant (7, 4)   |

### Constraints
1. **Precedence**: For each shipment, the pickup must be visited before the delivery.
2. **Capacity**: Each vehicle can carry at most 3 shipments simultaneously (load ≤ 3).
3. **Coverage**: Every shipment must be fully assigned (pickup + delivery) to exactly one vehicle.
4. **Routing**: Every vehicle starts and ends at the depot.

---

## Scoring Formula

```
score = min(1000, round(1000 × reference_distance / student_distance))
```

- A score of **1000** means the student matched the reference (heuristic) solution exactly.
- Scores > 1000 are not possible (capped at 1000).
- If the solution is **infeasible** (any constraint violated), score = 0.
- Only feasible solutions appear on the leaderboard.

---

## File Structure

```
IE105000_2_VRP/
├── app.py          — Streamlit UI (all 4 tabs, map drawing, click interaction)
├── scenario.py     — Pure data: DEPOT, LOCATIONS, SHIPMENTS, VEHICLES
├── engine.py       — Route evaluation: distance, feasibility checking
├── solver.py       — Reference solver: enumeration + nearest-neighbour heuristic
├── db.py           — Google Sheets leaderboard (gspread)
├── requirements.txt
├── .gitignore
└── CLAUDE.md       — This file
```

---

## Game Flow

1. **Tab 1 — Scenario**: Student reads the problem description, map, shipment table, constraints.
2. **Tab 2 — Plan Routes**: Student builds routes interactively:
   - Select active vehicle (V1 blue / V2 amber)
   - Click location nodes on the Plotly map to append to the active vehicle's route
   - Real-time feedback: load, distance, constraint violations
   - Undo last stop / Clear vehicle route
   - When all 10 stops are assigned and feasible → Submit button activates
3. **Tab 3 — Solution**: After submit, shows side-by-side comparison of student vs reference routes, score, and learning reflection.
4. **Tab 4 — Leaderboard**: Top feasible submissions ranked by score (highest = best).

---

## Key Implementation Notes

### app.py

**Session state keys:**
- `vrp_routes`: `{"v1": [...], "v2": [...]}` — ordered lists of location IDs
- `vrp_active_vehicle`: `"v1"` or `"v2"`
- `vrp_submitted`: bool — True after successful submission
- `vrp_evaluation`: full evaluation dict from `engine.evaluate_solution()`
- `vrp_student_name`: string
- `vrp_reference`: reference solution dict from `solver.solve()`
- `vrp_score`: integer 0–1000
- `vrp_active_tab`: integer (tab index, used for post-submit navigation)

**`draw_map(routes, active_vehicle, highlight_clickable)`:**
- Returns a Plotly `go.Figure`
- Uses `clickmode="event+select"` and `dragmode=False`
- Each location node has `customdata=[[loc_id]]` for click detection
- Depot has `customdata=[["depot"]]` but click is ignored
- Draws: shipment pair dashed lines → vehicle route lines → location nodes → depot → annotations

**Click handling:**
- Uses `st.plotly_chart(..., on_select="rerun", selection_mode=("points",))`
- Reads `event.selection["points"][0]["customdata"]`
- Validates before appending: not already assigned, precedence check for deliveries, capacity check for pickups

**Graceful degradation:**
- `db.py` is imported in a `try/except` block at the top of `app.py`
- If `_DB_AVAILABLE = False`, leaderboard tab shows a warning and submit skips saving

### solver.py

Uses brute-force enumeration of all 2-partitions of 5 shipments:
- 2^5 − 2 = 30 non-trivial splits (excluding all-to-one cases)
- Each split is expanded to location-level stop lists
- Nearest-neighbour heuristic sequences each vehicle's stops (respecting precedence)
- Returns the partition+sequence with minimum total distance

### engine.py

- `route_distance(stop_ids)`: depot → stops → depot, Euclidean distance
- `check_route(stop_ids, vehicle_id)`: validates capacity and precedence, returns `(feasible, violations, load_profile)`
- `evaluate_solution(routes)`: checks coverage, duplicates, then calls check_route per vehicle

### db.py

Google Sheets worksheet: `vrp_routes`

Headers: `id, student_name, played_at, total_distance, reference_distance, gap_pct, score, feasible, v1_route, v2_route, n_violations`

Leaderboard ranks by `score DESC`, only feasible entries.

Streamlit secrets required:
```toml
gcp_json = '{"type": "service_account", ...}'
[sheet]
id = "YOUR_GOOGLE_SHEET_ID"
```

---

## Educational Goals

A student completing one round should understand:

1. **Routing problem structure**: Nodes, edges, depot, and the objective of minimising total travel.
2. **Capacity constraint**: Vehicles have limited load; full vehicles must deliver before picking up more.
3. **Precedence constraint**: In pickup-and-delivery problems, order matters — you cannot deliver something you haven't collected.
4. **Combinatorial complexity**: Even with 5 shipments and 2 vehicles, the number of possible routes is large.
5. **Heuristic vs optimal**: The solver uses a nearest-neighbour heuristic — it's fast but not guaranteed optimal. Students who outscore the reference found a better route than the heuristic.
6. **Spatial intuition**: Clustering geographically close pickups/deliveries onto one vehicle tends to reduce total distance.
7. **Vehicle routing in practice**: Real-world PD-VRP is NP-hard; this game gives a taste of why logistics optimisation is a rich research field.

---

## VRP Concepts Glossary

| Term | Meaning |
|------|---------|
| VRP | Vehicle Routing Problem — assign customers to routes to minimise cost |
| PD-VRP | Pickup and Delivery VRP — each job has both a source and destination |
| Capacity constraint | Vehicle load ≤ vehicle capacity at all times |
| Precedence constraint | Pickup must precede delivery for same shipment |
| Nearest-neighbour heuristic | Greedy route construction: always go to the closest eligible next stop |
| Feasible solution | All constraints satisfied |
| Infeasible solution | At least one constraint violated (score = 0) |
| Gap % | (Student distance − Reference distance) / Reference distance × 100 |

---

## Pending / Future Work

- Time windows (VRPTW): add time constraints for each location
- More vehicles and shipments for advanced sessions
- Instructor mode: edit scenario parameters (demands, locations, capacity)
- Optimal solver (exact ILP) for comparison
- CSV export of submitted solutions
- Scenario B: humanitarian aid distribution (different educational framing)
