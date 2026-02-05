import csv
from datetime import datetime

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

    km_at_service = int(form.get("km_at_service", 0))
    service_target_km = int(form.get("service_target_km", 0))

    km_difference = km_at_service - service_target_km

    new_service = {
        "truck_reg": form.get("truck_reg"),
        "service_date": form.get("service_date"),
        "km_at_service": str(km_at_service),
        "service_target_km": str(service_target_km),
        "service_place": form.get("service_place"),
        "km_difference": str(km_difference),
        "service_type": form.get("service_type"),
        "notes": form.get("notes"),
    }

    services.append(new_service)
    save_services(services)
    return True
