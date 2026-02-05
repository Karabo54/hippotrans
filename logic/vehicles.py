import csv
from datetime import datetime, timedelta

VEHICLE_FILE = "DATA/vehicles.csv"
SERVICE_INTERVAL_KM = 40000  # adjust as needed


def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_vehicles():
    vehicles = []
    try:
        with open(VEHICLE_FILE, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                vehicles.append(row)
    except FileNotFoundError:
        pass
    return vehicles


def save_vehicles(vehicles):
    if not vehicles:
        return

    fieldnames = vehicles[0].keys()
    with open(VEHICLE_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(vehicles)


def calculate_service_status(vehicle):
    current_km = safe_int(vehicle.get("current_km"))
    last_service_km = safe_int(vehicle.get("last_service_km"))

    km_since_service = current_km - last_service_km
    km_to_service = SERVICE_INTERVAL_KM - km_since_service

    if km_to_service <= 0:
        return "OVERDUE", km_to_service
    elif km_to_service <= 1000:
        return "DUE", km_to_service
    else:
        return "OK", km_to_service


def km_update_required(vehicle):
    last_update = vehicle.get("last_km_update")
    if not last_update:
        return True

    last_update_date = datetime.strptime(last_update, "%Y-%m-%d").date()
    today = datetime.today().date()
    monday = today - timedelta(days=today.weekday())

    return last_update_date < monday


def update_vehicle_km_from_trip(truck_reg, new_km):
    vehicles = load_vehicles()
    updated = False

    for v in vehicles:
        if v.get("truck_reg") == truck_reg:
            current_km = safe_int(v.get("current_km"))
            if new_km > current_km:
                v["current_km"] = new_km
                v["last_km_update"] = datetime.today().strftime("%Y-%m-%d")
                updated = True
            break

    if updated:
        save_vehicles(vehicles)

    return updated
