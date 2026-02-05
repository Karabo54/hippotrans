import csv
from datetime import date, datetime

DATA_PATH = "DATA"

def load_csv(file_name):
    records = []
    try:
        with open(f"{DATA_PATH}/{file_name}", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                records.append(row)
    except FileNotFoundError:
        print(f"⚠️ Missing file: {file_name}")
    return records


def load_dashboard_stats():
    vehicles = load_csv("vehicles.csv")
    trips = load_csv("trips.csv")
    breakdowns = load_csv("breakdowns.csv")
    compliance = load_csv("compliance.csv")
    fuel = load_csv("fuel.csv")

    today = date.today()

    # Vehicles
    total_vehicles = len(vehicles)
    active_vehicles = sum(1 for v in vehicles if v.get("status", "").lower() == "active")

    # Trips
    total_trips = len(trips)

    # Breakdowns
    open_breakdowns = sum(1 for b in breakdowns if b.get("status", "").lower() != "resolved")

    # Compliance
    expired_docs = 0
    almost_due_docs = 0

    for r in compliance:
        try:
            expiry = datetime.strptime(r["expiry_date"], "%Y-%m-%d").date()
            days_left = (expiry - today).days

            if r["doc_type"] == "Meter Calibration Certificate":
                limit = 50
            else:
                limit = 30

            if days_left < 0:
                expired_docs += 1
            elif days_left <= limit:
                almost_due_docs += 1
        except:
            continue

    # Fuel
    total_fuel_litres = 0
    total_fuel_cost = 0

    for f in fuel:
        try:
            total_fuel_litres += float(f.get("litres", 0))
            total_fuel_cost += float(f.get("cost", 0))
        except:
            continue

    return {
        "total_vehicles": total_vehicles,
        "active_vehicles": active_vehicles,
        "total_trips": total_trips,
        "open_breakdowns": open_breakdowns,
        "expired_docs": expired_docs,
        "almost_due_docs": almost_due_docs,
        "total_fuel_litres": round(total_fuel_litres, 2),
        "total_fuel_cost": round(total_fuel_cost, 2)
    }
