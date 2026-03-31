"""solver.py — Reference solution via enumeration + nearest-neighbour."""
from itertools import combinations
from engine import route_distance, check_route, dist, get_loc
from scenario import LOCATIONS, SHIPMENTS, VEHICLES


def _nn_route(stop_ids):
    """Nearest-neighbour sequencing respecting pickup-before-delivery precedence."""
    if not stop_ids:
        return []

    # Map: delivery → pickup for precedence
    pickup_of = {sh["delivery"]: sh["pickup"] for sh in SHIPMENTS.values()}

    remaining = list(stop_ids)
    route = []
    current = "depot"

    while remaining:
        # Only consider stops whose pickup prerequisite is already in route (or is pickup itself)
        candidates = []
        for s in remaining:
            loc = LOCATIONS[s]
            if loc["type"] == "pickup":
                candidates.append(s)
            else:  # delivery — pickup must already be placed
                pid = pickup_of[s]
                if pid in route:
                    candidates.append(s)

        if not candidates:
            # Fallback: force remaining pickups first
            candidates = [s for s in remaining if LOCATIONS[s]["type"] == "pickup"]
            if not candidates:
                candidates = remaining  # should not happen if data is consistent

        # Pick nearest candidate
        cur_loc = get_loc(current)
        best = min(candidates, key=lambda s: dist(cur_loc, get_loc(s)))
        route.append(best)
        remaining.remove(best)
        current = best

    return route


def solve():
    """
    Enumerate all 2-partition assignments of 5 shipments to 2 vehicles.
    For each feasible assignment, apply NN sequencing and keep the best.
    Returns dict with best routes and total distance.
    """
    shipment_ids = list(SHIPMENTS.keys())
    best_dist = float("inf")
    best_routes = None

    # All non-empty subsets for v1 (complement goes to v2)
    for r in range(1, len(shipment_ids)):
        for v1_ships in combinations(shipment_ids, r):
            v2_ships = [s for s in shipment_ids if s not in v1_ships]
            if not v2_ships:
                continue

            # Expand to stops
            v1_stops = [loc for s in v1_ships for loc in [SHIPMENTS[s]["pickup"], SHIPMENTS[s]["delivery"]]]
            v2_stops = [loc for s in v2_ships for loc in [SHIPMENTS[s]["pickup"], SHIPMENTS[s]["delivery"]]]

            # Check capacity
            if len(v1_ships) > VEHICLES["v1"]["capacity"] or len(v2_ships) > VEHICLES["v2"]["capacity"]:
                continue

            # Sequence with NN
            r1 = _nn_route(v1_stops)
            r2 = _nn_route(v2_stops)

            # Check feasibility
            ok1, _, _ = check_route(r1, "v1")
            ok2, _, _ = check_route(r2, "v2")
            if not (ok1 and ok2):
                continue

            total = route_distance(r1) + route_distance(r2)
            if total < best_dist:
                best_dist = total
                best_routes = {"v1": r1, "v2": r2}

    return {
        "routes": best_routes,
        "total_distance": best_dist,
    }
