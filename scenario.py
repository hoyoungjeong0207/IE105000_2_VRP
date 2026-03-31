"""scenario.py — Location pool and scenario generator for VRP game."""
import random

DEPOT = {"id": "depot", "name": "Warehouse", "x": 5.0, "y": 5.0}

# Pool of 16 named locations with fixed coordinates
LOCATION_POOL = [
    {"id": "A",  "name": "Bakery",           "icon": "🥖", "x": 1.0, "y": 8.0},
    {"id": "B",  "name": "Electronics",      "icon": "📱", "x": 8.0, "y": 2.0},
    {"id": "C",  "name": "Flower Market",    "icon": "💐", "x": 1.0, "y": 3.0},
    {"id": "D",  "name": "Print Shop",       "icon": "🖨️", "x": 9.0, "y": 7.0},
    {"id": "E",  "name": "Café Supply",      "icon": "☕", "x": 4.0, "y": 9.0},
    {"id": "F",  "name": "Office Tower",     "icon": "🏢", "x": 9.0, "y": 9.0},
    {"id": "G",  "name": "University Lab",   "icon": "🔬", "x": 2.0, "y": 1.0},
    {"id": "H",  "name": "Hospital",         "icon": "🏥", "x": 8.0, "y": 6.0},
    {"id": "I",  "name": "School",           "icon": "🏫", "x": 3.0, "y": 2.0},
    {"id": "J",  "name": "Restaurant",       "icon": "🍽️", "x": 7.0, "y": 4.0},
    {"id": "K",  "name": "Supermarket",      "icon": "🛒", "x": 2.0, "y": 6.0},
    {"id": "L",  "name": "Pharmacy",         "icon": "💊", "x": 6.0, "y": 8.0},
    {"id": "M",  "name": "Library",          "icon": "📚", "x": 4.0, "y": 2.0},
    {"id": "N",  "name": "Museum",           "icon": "🏛️", "x": 7.0, "y": 9.0},
    {"id": "O",  "name": "Post Office",      "icon": "📮", "x": 3.0, "y": 7.0},
    {"id": "P",  "name": "Sports Center",    "icon": "🏟️", "x": 8.0, "y": 4.0},
]

# Colors for numbered pairs (up to 6 pairs)
PAIR_COLORS = ["#ef4444", "#3b82f6", "#22c55e", "#a855f7", "#f97316", "#06b6d4"]

# Vehicle colors (up to 3 vehicles)
VEHICLE_COLORS = ["#facc15", "#f472b6", "#34d399"]  # yellow, pink, mint

DEFAULT_NUM_VEHICLES  = 2
DEFAULT_NUM_SHIPMENTS = 4


def generate_scenario(num_vehicles: int, num_shipments: int, seed: int):
    """
    Randomly pick 2*num_shipments locations from LOCATION_POOL (no repeats).
    First num_shipments become pickups, next num_shipments become deliveries.
    Pair pickup i with delivery i → shipment i+1.

    Returns (locations, shipments, vehicles) as dicts.
    """
    import math
    rng = random.Random(seed)
    chosen = rng.sample(LOCATION_POOL, num_shipments * 2)
    pickups    = chosen[:num_shipments]
    deliveries = chosen[num_shipments:]

    # Capacity: each vehicle can handle ceil(num_shipments / num_vehicles) + 1
    cap = math.ceil(num_shipments / num_vehicles) + 1

    locations = {}
    shipments = {}
    for i, (p, d) in enumerate(zip(pickups, deliveries), start=1):
        pid = f"p{i}"
        did = f"d{i}"
        sid = f"s{i}"
        locations[pid] = {
            "id": pid, "name": p["name"], "icon": p["icon"],
            "type": "pickup", "x": p["x"], "y": p["y"],
            "shipment": sid, "pair_num": i,
        }
        locations[did] = {
            "id": did, "name": d["name"], "icon": d["icon"],
            "type": "delivery", "x": d["x"], "y": d["y"],
            "shipment": sid, "pair_num": i,
        }
        shipments[sid] = {
            "id": sid, "name": f"Shipment {i}",
            "pickup": pid, "delivery": did, "demand": 1,
            "pair_num": i,
        }

    vehicles = {}
    veh_ids = [f"v{i}" for i in range(1, num_vehicles + 1)]
    for i, vid in enumerate(veh_ids):
        vehicles[vid] = {
            "id": vid, "name": f"Vehicle {i+1}",
            "capacity": cap, "color": VEHICLE_COLORS[i],
        }

    return locations, shipments, vehicles
