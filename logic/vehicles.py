import csv
from datetime import datetime, timedelta

VEHICLE_FILE = "DATA/vehicles.csv"
SERVICE_INTERVAL_KM = 40000  # adjust as needed


def safe_int(value):
    """Safely converts input to an integer, handling floats like '227758.0'."""
    try:
        if value is None or value == "":
            return 0
        # Convert to float first to handle the .0, then to int
        return int(float(str(value).replace(',', '')))
    except (ValueError, TypeError):
        return 0


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
    
def auto_update_all_vehicle_km():
    """Aggregates KM from all trip files, prints max found per truck, and updates registry."""
    data_sources = {
        "DATA/trips.csv": {"load": "loading_km", "off": "offloading_km"},
        "DATA/secondary_trips.csv": {"load": "loading_km", "off": "offloading_km"},
        "DATA/puma_trips.csv": {"load": "loading_km", "off": "offloading_km"},
        "DATA/breakdowns.csv": {"load": "km_at_breakdown", "off": "km_at_breakdown"},
        "DATA/puma_secondary_trips.csv": {"load": "loading_km", "off": "offloading_km"}
    }

    vehicles = load_vehicles()
    vehicle_map = {str(v.get("truck_reg", "")).strip().upper(): v for v in vehicles}
    
    # 1. Dictionary to hold the absolute max KM found for each truck across ALL files
    max_kms_found = {}

    # 2. First Pass: Scan all files to find the max KM for each truck
    for file_path, cols in data_sources.items():
        try:
            with open(file_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    raw_reg = str(row.get("truck_reg", "")).strip().upper()
                    
                    if raw_reg not in vehicle_map:
                        continue
                    
                    # DEBUG: Print the raw values found
                    load_val = row.get(cols["load"], "0")
                    off_val = row.get(cols["off"], "0")
                    
                    val1 = safe_int(load_val)
                    val2 = safe_int(off_val)
                    
                    
                    
                    trip_max = max(val1, val2)
                    max_kms_found[raw_reg] = max(max_kms_found.get(raw_reg, 0), trip_max)
        except FileNotFoundError:
            continue


    # 4. Second Pass: Update registry if discovery is higher than current
    today_str = datetime.today().strftime("%Y-%m-%d")
    updated = False

    for reg, candidate_km in max_kms_found.items():
        vehicle = vehicle_map[reg]
        current_stored_km = safe_int(vehicle.get("current_km", 0))

        if candidate_km > current_stored_km:
            vehicle["current_km"] = str(candidate_km)
            vehicle["last_km_update"] = today_str
            if not vehicle.get("last_service_km"):
                vehicle["last_service_km"] = str(candidate_km)
            updated = True
       

    if updated:
        save_vehicles(vehicles)

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
                if new_km - current_km < 1500:
                    v["current_km"] = new_km
                    v["last_km_update"] = datetime.today().strftime("%Y-%m-%d")
                    updated = True
                else:
                    break
            break

    if updated:
        save_vehicles(vehicles)

    return updated
    
def record_service_completed(truck_reg, service_km, interval):
    """
    Call this when a truck finishes a service.
    Example: record_service_completed("BZ 12 GP", 400000, 50000)
    Sets next service to 450,000km.
    """
    vehicles = load_vehicles()
    for v in vehicles:
        if v.get("truck_reg") == truck_reg:
            v["last_service_km"] = str(service_km)
            v["next_service_km"] = str(service_km + interval)
            v["current_km"] = str(service_km) # Sync current km to service km
            break
    save_vehicles(vehicles)