"""scenario.py — Instance data for the IE105000 VRP Pickup & Delivery Game."""

DEPOT = {"id": "depot", "name": "Central Warehouse", "x": 5.0, "y": 5.0}

LOCATIONS = {
    "p1": {"id": "p1", "name": "Bakery",             "type": "pickup",   "x": 1.0, "y": 8.0, "shipment": "s1", "icon": "🥖"},
    "d1": {"id": "d1", "name": "Office Tower",        "type": "delivery", "x": 9.0, "y": 9.0, "shipment": "s1", "icon": "🏢"},
    "p2": {"id": "p2", "name": "Electronics Store",   "type": "pickup",   "x": 8.0, "y": 2.0, "shipment": "s2", "icon": "📱"},
    "d2": {"id": "d2", "name": "University Lab",      "type": "delivery", "x": 2.0, "y": 1.0, "shipment": "s2", "icon": "🔬"},
    "p3": {"id": "p3", "name": "Flower Market",       "type": "pickup",   "x": 1.0, "y": 3.0, "shipment": "s3", "icon": "💐"},
    "d3": {"id": "d3", "name": "Hospital",            "type": "delivery", "x": 8.0, "y": 6.0, "shipment": "s3", "icon": "🏥"},
    "p4": {"id": "p4", "name": "Print Shop",          "type": "pickup",   "x": 9.0, "y": 7.0, "shipment": "s4", "icon": "🖨️"},
    "d4": {"id": "d4", "name": "School",              "type": "delivery", "x": 3.0, "y": 2.0, "shipment": "s4", "icon": "🏫"},
    "p5": {"id": "p5", "name": "Café Supply",         "type": "pickup",   "x": 4.0, "y": 9.0, "shipment": "s5", "icon": "☕"},
    "d5": {"id": "d5", "name": "Restaurant",          "type": "delivery", "x": 7.0, "y": 4.0, "shipment": "s5", "icon": "🍽️"},
}

SHIPMENTS = {
    "s1": {"id": "s1", "name": "Fresh Bread",    "pickup": "p1", "delivery": "d1", "demand": 1},
    "s2": {"id": "s2", "name": "Lab Equipment",  "pickup": "p2", "delivery": "d2", "demand": 1},
    "s3": {"id": "s3", "name": "Flowers",        "pickup": "p3", "delivery": "d3", "demand": 1},
    "s4": {"id": "s4", "name": "Documents",      "pickup": "p4", "delivery": "d4", "demand": 1},
    "s5": {"id": "s5", "name": "Café Supplies",  "pickup": "p5", "delivery": "d5", "demand": 1},
}

VEHICLES = {
    "v1": {"id": "v1", "name": "Vehicle 1", "capacity": 3, "color": "#3b82f6"},
    "v2": {"id": "v2", "name": "Vehicle 2", "capacity": 3, "color": "#f59e0b"},
}
