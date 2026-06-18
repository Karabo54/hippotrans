import csv
from datetime import datetime
from logic.vehicles import load_vehicles

SERVICES_FILE = "DATA/service_history.csv"

def load_services():
    services = []
    try:
        with open(SERVICES_FILE, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                services.append(row)
    except FileNotFoundError:
        pass
    return services


def save_services(services):
    if not services:
        return

    fieldnames = services[0].keys()
    with open(SERVICES_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(services)


def add_service_entry(form):
    services = load_services()
    vehicles = load_vehicles()

    # 1. Get current vehicle data to find the "Previous Target"
    truck_reg = form.get("truck_reg")
    vehicle = next((v for v in vehicles if v.get("truck_reg") == truck_reg), {})
    
    # The "Previous Target" is what was stored in the vehicle master list before this update
    previous_target = int(vehicle.get("next_service_km") or 0)
    
    # 2. Get data from the new form
    current_service_km = int(form.get("service_km", 0))
    next_goal_km = int(form.get("next_service_km", 0))

    # 3. Calculate KM Difference (How late/early the truck was)
    # Negative means early, Positive means late
    diff = 0
    if previous_target > 0:
        diff = current_service_km - previous_target

    # 4. Create the new entry with matching keys for your CSV
    new_entry = {
        "truck_reg": truck_reg,
        "service_date": form.get("service_date"),
        "service_km": current_service_km,
        "next_service_km": next_goal_km,
        "service_place": form.get("service_place"),
        "km_difference": diff,
        "service_type": form.get("service_type"),
        "notes": form.get("notes")
    }

    # 5. Append and Save
    services.append(new_entry)
    save_services(services)
    return True
