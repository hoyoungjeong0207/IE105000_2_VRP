"""engine.py — Route evaluation for the VRP game."""
import math
from scenario import DEPOT, LOCATIONS, SHIPMENTS, VEHICLES


def dist(a, b):
    return math.sqrt((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2)


def get_loc(loc_id):
    return DEPOT if loc_id == "depot" else LOCATIONS[loc_id]


def route_distance(stop_ids):
    """Total distance of depot→stops→depot."""
    full = ["depot"] + list(stop_ids) + ["depot"]
    return sum(dist(get_loc(full[i]), get_loc(full[i + 1])) for i in range(len(full) - 1))


def check_route(stop_ids, vehicle_id):
    """Return (feasible, violations, load_profile) for a single vehicle route."""
    capacity = VEHICLES[vehicle_id]["capacity"]
    load = 0
    picked = set()
    violations = []
    load_profile = [0]

    for sid in stop_ids:
        loc = LOCATIONS[sid]
        shipment_id = loc["shipment"]
        if loc["type"] == "pickup":
            load += SHIPMENTS[shipment_id]["demand"]
            picked.add(shipment_id)
            if load > capacity:
                violations.append(f"Capacity exceeded at {loc['name']} (load={load})")
        else:  # delivery
            if shipment_id not in picked:
                violations.append(f"Delivered {loc['name']} before picking up shipment {shipment_id}")
            else:
                load -= SHIPMENTS[shipment_id]["demand"]
        load_profile.append(load)

    return len(violations) == 0, violations, load_profile


def evaluate_solution(routes):
    """
    routes: {"v1": [stop_ids], "v2": [stop_ids]}
    Returns full evaluation dict.
    """
    all_stops = [s for stops in routes.values() for s in stops]
    covered = {s for s in all_stops if s in LOCATIONS}

    missing = []
    for sid, sh in SHIPMENTS.items():
        if sh["pickup"] not in covered:
            missing.append(f"Shipment {sid} ({sh['name']}): pickup not assigned")
        if sh["delivery"] not in covered:
            missing.append(f"Shipment {sid} ({sh['name']}): delivery not assigned")

    # Check duplicates
    duplicates = []
    seen = set()
    for s in all_stops:
        if s in seen:
            duplicates.append(f"{LOCATIONS[s]['name']} assigned to multiple vehicles")
        seen.add(s)

    total_dist = 0
    route_results = {}
    all_violations = list(missing) + list(duplicates)

    for vid, stop_ids in routes.items():
        feasible, viol, load_profile = check_route(stop_ids, vid)
        d = route_distance(stop_ids)
        route_results[vid] = {
            "stops": stop_ids,
            "distance": d,
            "feasible": feasible,
            "violations": viol,
            "load_profile": load_profile,
            "n_stops": len(stop_ids),
        }
        total_dist += d
        all_violations.extend(viol)

    return {
        "total_distance": total_dist,
        "feasible": len(all_violations) == 0,
        "violations": all_violations,
        "route_results": route_results,
    }
