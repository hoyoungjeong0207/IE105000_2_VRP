"""engine.py — Route evaluation for VRP game (scenario passed as parameters)."""
import math
from scenario import DEPOT


def dist(a, b):
    return math.sqrt((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2)


def get_loc(loc_id, locations):
    if loc_id == "depot":
        return DEPOT
    return locations[loc_id]


def route_distance(stop_ids, locations):
    if not stop_ids:
        return 0.0
    pts = [DEPOT] + [locations[s] for s in stop_ids] + [DEPOT]
    return sum(dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def check_route(stop_ids, vehicle_id, locations, shipments, vehicles):
    """Returns (feasible, violations, load_profile)."""
    cap = vehicles[vehicle_id]["capacity"]
    pickup_of = {sh["delivery"]: sh["pickup"] for sh in shipments.values()}
    violations = []
    load = 0
    load_profile = []
    visited = set()
    for sid in stop_ids:
        loc = locations[sid]
        if loc["type"] == "delivery":
            pid = pickup_of.get(sid)
            if pid and pid not in visited:
                violations.append(f"Delivery {loc['name']} before its pickup")
        if loc["type"] == "pickup":
            load += shipments[loc["shipment"]]["demand"]
        else:
            load -= shipments[loc["shipment"]]["demand"]
        if load > cap:
            violations.append(f"Over capacity ({load}/{cap}) at {loc['name']}")
        load_profile.append(load)
        visited.add(sid)
    return (len(violations) == 0, violations, load_profile)


def evaluate_solution(routes, locations, shipments, vehicles):
    """Full feasibility check and distance computation."""
    violations = []
    route_results = {}
    total_dist = 0.0

    for vid, stop_ids in routes.items():
        ok, viol, lp = check_route(stop_ids, vid, locations, shipments, vehicles)
        d = route_distance(stop_ids, locations)
        total_dist += d
        route_results[vid] = {
            "stops": stop_ids,
            "feasible": ok,
            "violations": viol,
            "distance": d,
            "load_profile": lp,
        }
        violations.extend(viol)

    # Check coverage
    for sid, sh in shipments.items():
        for loc_id in [sh["pickup"], sh["delivery"]]:
            count = sum(1 for stops in routes.values() if loc_id in stops)
            if count == 0:
                violations.append(f"Stop {loc_id} not assigned")
            elif count > 1:
                violations.append(f"Stop {loc_id} assigned to multiple vehicles")

        # Pickup and delivery must be in same vehicle
        p_in = [vid for vid, stops in routes.items() if sh["pickup"] in stops]
        d_in = [vid for vid, stops in routes.items() if sh["delivery"] in stops]
        if p_in and d_in and p_in[0] != d_in[0]:
            violations.append(f"Shipment {sid}: pickup and delivery in different vehicles")

    return {
        "feasible": len(violations) == 0,
        "violations": violations,
        "total_distance": total_dist,
        "route_results": route_results,
    }
