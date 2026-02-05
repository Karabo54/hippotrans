import csv
import os
from logic.vehicles import load_vehicles

SERVICE_FILE = "DATA/services.csv"

def ensure_service_file():
    if not os.path.exists(SERVICE_FILE):
        with open(SERVICE_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "reg_number",
                "service_date",
                "km_at_service",
                "service_type",
                "notes"
            ])

def load_services():
    ensure_service_file()
    services = []
    with open(SERVICE_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            services.append(row)
    return services

def add_service(form_data):
    with open(SERVICE_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            form_data.get("reg_number"),
            form_data.get("service_date"),
            form_data.get("km_at_service"),
            form_data.get("service_type"),
            form_data.get("notes")
        ])

def calculate_service_status(vehicle):
    """
    Returns:
    - km_since_service
    - km_remaining
    - status: OK / DUE / OVERDUE
    """
    current_km = int(vehicle["current_km"])
    last_service_km = int(vehicle["last_service_km"])
    interval = int(vehicle["service_interval_km"])

    km_since = current_km - last_service_km
    km_remaining = interval - km_since

    if km_remaining <= 0:
        status = "OVERDUE"
    elif km_remaining <= 1000:
        status = "DUE"
    else:
        status = "OK"

    return km_since, km_remaining, status
