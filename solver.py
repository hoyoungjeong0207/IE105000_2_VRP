"""solver.py — Exact optimal solver for PD-VRP via backtracking."""
import math
from itertools import product
from engine import dist, get_loc, route_distance
from scenario import DEPOT


def _exact_route(shipment_ids, capacity, locations, shipments):
    """
    Find the exact optimal stop sequence for one vehicle given its assigned shipments.
    Uses branch-and-bound backtracking.
    Returns (best_route, best_distance).
    """
    if not shipment_ids:
        return [], 0.0

    stops = []
    for sid in shipment_ids:
        stops.append(shipments[sid]["pickup"])
        stops.append(shipments[sid]["delivery"])

    pickup_of = {shipments[sid]["delivery"]: shipments[sid]["pickup"] for sid in shipment_ids}

    best = [float("inf"), []]

    def bt(route, remaining, visited, load, d_so_far):
        if d_so_far >= best[0]:
            return  # prune
        if not remaining:
            last = get_loc(route[-1] if route else "depot", locations)
            total = d_so_far + dist(last, DEPOT)
            if total < best[0]:
                best[0] = total
                best[1] = list(route)
            return
        cur = get_loc(route[-1] if route else "depot", locations)
        for s in remaining:
            loc = locations[s]
            if loc["type"] == "delivery" and pickup_of.get(s) not in visited:
                continue
            new_load = load + (1 if loc["type"] == "pickup" else -1)
            if new_load > capacity:
                continue
            new_rem = [x for x in remaining if x != s]
            d_step = dist(cur, locations[s])
            bt(route + [s], new_rem, visited | {s}, new_load, d_so_far + d_step)

    bt([], stops, set(), 0, 0.0)
    return best[1], best[0]


def solve(locations, shipments, vehicles):
    """
    Find exact optimal routes by enumerating all vehicle-to-shipment assignments.
    Each shipment is assigned to exactly one vehicle.
    """
    shipment_ids = list(shipments.keys())
    vehicle_ids  = list(vehicles.keys())
    n = len(shipment_ids)
    v = len(vehicle_ids)

    best_dist   = float("inf")
    best_routes = None

    # Enumerate all v^n assignments
    for assignment in product(range(v), repeat=n):
        # Group shipments per vehicle
        per_veh = {vid: [] for vid in vehicle_ids}
        for ship_idx, veh_idx in enumerate(assignment):
            per_veh[vehicle_ids[veh_idx]].append(shipment_ids[ship_idx])

        # Check capacity
        feasible = True
        for vid, sids in per_veh.items():
            if len(sids) > vehicles[vid]["capacity"]:
                feasible = False
                break
        if not feasible:
            continue

        # Find optimal route per vehicle and sum distances
        total = 0.0
        routes = {}
        for vid, sids in per_veh.items():
            route, d = _exact_route(sids, vehicles[vid]["capacity"], locations, shipments)
            routes[vid] = route
            total += d

        if total < best_dist:
            best_dist = total
            best_routes = {vid: list(r) for vid, r in routes.items()}

    return {"routes": best_routes, "total_distance": best_dist}
