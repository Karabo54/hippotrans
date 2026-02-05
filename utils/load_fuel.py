import csv
from datetime import datetime
from collections import defaultdict

FUEL_FILE = "DATA/fuel.csv"


def safe_int(val):
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return 0


def safe_float(val):
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def load_fuel():
    try:
        with open(FUEL_FILE, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return []


def save_fuel(fuel_logs):
    if not fuel_logs:
        return

    fieldnames = fuel_logs[0].keys()
    with open(FUEL_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(fuel_logs)


def add_fuel_entry(form):
    fuel_logs = load_fuel()

    new_entry = {
        "date": form.get("date"),
        "truck_reg": form.get("truck_reg"),
        "driver": form.get("driver"),
        "litres": form.get("litres"),
        "fuel_station": form.get("fuel_station"),
        "km_at_fuel": form.get("km_at_fuel"),
        "cost": form.get("cost"),
        "reference": form.get("reference"),
        "notes": form.get("notes"),
    }

    fuel_logs.append(new_entry)
    save_fuel(fuel_logs)
    return True


def fuel_consumption_stats(fuel_logs, trips, month=None):
    by_truck = defaultdict(lambda: {"litres": 0, "km": 0, "l_per_100km": 0})
    by_route = defaultdict(lambda: {"litres": 0, "km": 0, "l_per_100km": 0})
    by_driver = defaultdict(lambda: {"litres": 0, "km": 0, "l_per_100km": 0})
    by_customer = defaultdict(lambda: {"litres": 0, "km": 0, "l_per_100km": 0})

    # Filter fuel logs by month
    filtered_fuel = []
    for log in fuel_logs:
        try:
            log_month = datetime.strptime(log.get("date"), "%Y-%m-%d").strftime("%Y-%m")
        except:
            continue

        if month and log_month != month:
            continue

        filtered_fuel.append(log)

    # Build KM from trips
    for trip in trips:
        if trip.get("status") != "OFFLOADED":
            continue

        try:
            trip_month = datetime.strptime(trip.get("date_offloaded"), "%Y-%m-%d").strftime("%Y-%m")
        except:
            continue

        if month and trip_month != month:
            continue

        km = safe_int(trip.get("km_travelled"))
        truck = trip.get("truck_reg")
        route = trip.get("offloading_point")
        driver = trip.get("driver")
        customer = trip.get("customer")

        if truck:
            by_truck[truck]["km"] += km
        if route:
            by_route[route]["km"] += km
        if driver:
            by_driver[driver]["km"] += km
        if customer:
            by_customer[customer]["km"] += km

    # Add fuel
    for log in filtered_fuel:
        truck = log.get("truck_reg")
        driver = log.get("driver")
        litres = safe_float(log.get("litres"))

        if truck:
            by_truck[truck]["litres"] += litres
        if driver:
            by_driver[driver]["litres"] += litres

    # Calculate efficiency
    for dataset in [by_truck, by_route, by_driver, by_customer]:
        for key, data in dataset.items():
            km = data["km"]
            litres = data["litres"]
            data["l_per_100km"] = round((litres / km) * 100, 2) if km > 0 else 0

    return {
        "by_truck": dict(by_truck),
        "by_route": dict(by_route),
        "by_driver": dict(by_driver),
        "by_customer": dict(by_customer),
    }
