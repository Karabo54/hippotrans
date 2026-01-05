import csv
from datetime import datetime

# Load drivers
drivers = {}
with open("data/drivers.csv", newline="") as file:
    reader = csv.DictReader(file)
    for row in reader:
        pdp_date = datetime.strptime(row["pdp_expiry"], "%Y-%m-%d")
        med_date = datetime.strptime(row["medical_expiry"], "%Y-%m-%d")
        today = datetime.today()
        # Determine status
        status = "ACTIVE"
        if pdp_date < today or med_date < today:
            status = "SUSPENDED"
        drivers[row["driver_id"]] = status

# Load vehicles
vehicles = {}
with open("data/vehicles.csv", newline="") as file:
    reader = csv.DictReader(file)
    for row in reader:
        road_date = datetime.strptime(row["roadworthy_expiry"], "%Y-%m-%d")
        dg_date = datetime.strptime(row["dg_expiry"], "%Y-%m-%d")
        today = datetime.today()
        status = "COMPLIANT"
        if road_date < today or dg_date < today:
            status = "LOCKED"
        vehicles[row["vehicle_id"]] = status

# Load trips and check compliance
with open("data/fuel_trips.csv", newline="") as file:
    reader = csv.DictReader(file)
    print("TRIPS STATUS CHECK")
    print("-" * 80)
    for row in reader:
        trip_id = row["trip_id"]
        driver_id = row["driver_id"]
        vehicle_id = row["truck_id"]
        status = row["status"]

        # Check driver and vehicle
        driver_status = drivers.get(driver_id, "UNKNOWN")
        vehicle_status = vehicles.get(vehicle_id, "UNKNOWN")

        # Block trip if driver suspended or vehicle locked
        if driver_status != "ACTIVE":
            status = "BLOCKED (Driver)"
        elif vehicle_status != "COMPLIANT":
            status = "BLOCKED (Vehicle)"

        print(f"{trip_id} | Driver: {driver_id} ({driver_status}) | Truck: {vehicle_id} ({vehicle_status}) | Original: {row['status']} | Trip Status: {status}")
