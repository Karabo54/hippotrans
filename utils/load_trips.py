import csv
import os
from datetime import datetime, timedelta

from flask import flash

TRIPS_FILE = "DATA/trips.csv"


# -------------------- HELPERS --------------------

def safe_int(value):
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return 0

def safe_float(value):
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        return 0.0
# -------------------- CORE FUNCTIONS --------------------

def load_trips():
    if not os.path.exists(TRIPS_FILE):
        return []

    trips = []
    with open(TRIPS_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Ensure numeric fields are loaded as numbers
            row["litres_loaded"] = safe_int(row.get("litres_loaded"))
            row["litres_offloaded"] = safe_int(row.get("litres_offloaded"))
            row["loading_km"] = safe_int(row.get("loading_km"))
            row["offloading_km"] = safe_int(row.get("offloading_km"))
            row["difference"] = safe_int(row.get("difference"))
            row["km_travelled"] = safe_int(row.get("km_travelled"))

            trips.append(row)

    return trips


def save_trips(trips):
    if not trips:
        return

    fieldnames = trips[0].keys()
    with open(TRIPS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(trips)


def format_duration(total_minutes):
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return f"{hours} h {minutes:02d} m"

def calculate_km_and_time(trip):
    # KM travelled
    loading_km = safe_int(trip.get("loading_km"))
    offloading_km = safe_int(trip.get("offloading_km"))

    if loading_km and offloading_km and offloading_km > loading_km:
        trip["km_travelled"] = str(offloading_km - loading_km)
    else:
        trip["km_travelled"] = 0
       
        return

    # Litres difference
    litres_loaded = safe_int(trip.get("litres_loaded"))
    litres_offloaded = safe_int(trip.get("litres_offloaded"))

    if litres_loaded and litres_offloaded:
        trip["difference"] = str(round(litres_offloaded - litres_loaded, 2))
    else:
        trip["difference"] = "0"

    # Time taken (uses dates + times — as we fixed before)
    date_loaded = trip.get("date_loaded")
    offloading_date = trip.get("date_offloaded")
    loading_time = trip.get("loading_time")
    offloading_time = trip.get("offloading_time")

    if date_loaded and offloading_date and loading_time and offloading_time:
        try:
            start_dt = datetime.strptime(f"{date_loaded} {loading_time}", "%Y-%m-%d %H:%M")
            end_dt = datetime.strptime(f"{offloading_date} {offloading_time}", "%Y-%m-%d %H:%M")
            delta = end_dt - start_dt

            total_minutes = int(delta.total_seconds() // 60)
            hours = total_minutes // 60
            minutes = total_minutes % 60

            trip["time_taken"] = f"{hours} h {minutes:02d} m"
        except:
            trip["time_taken"] = ""
    else:
        trip["time_taken"] = ""

def add_trip(form_data):
    trips = load_trips()
    order_number = form_data.get("order_number")

    # Prevent duplicate order numbers
    if any(t.get("order_number") == order_number for t in trips):
        return False

    new_trip = dict(form_data)

    # Ensure all expected fields exist
    new_trip.setdefault("loading_km", "")
    new_trip.setdefault("offloading_km", "")
    new_trip.setdefault("loading_time", "")
    new_trip.setdefault("offloading_time", "")
    new_trip.setdefault("litres_loaded", "")
    new_trip.setdefault("litres_offloaded", "")
    new_trip.setdefault("difference", 0)
    new_trip.setdefault("km_travelled", 0)
    new_trip.setdefault("time_taken", "")

    calculate_km_and_time(new_trip)

    trips.append(new_trip)
    save_trips(trips)
    return True


# 1. Rename the helper function
def perform_trip_deletion(order_number):
    trips = load_trips()
    # Filter the list
    new_trips = [t for t in trips if str(t.get("order_number")) != str(order_number)]
    # Save the updated list
    save_trips(new_trips)

def update_trip(order_number, form_data):
    trips = load_trips()

    for trip in trips:
        if trip.get("order_number") == order_number:
            trip.update(form_data)
            calculate_km_and_time(trip)
            break

    save_trips(trips)


def update_status(order_number, status, position):
    trips = load_trips()

    for trip in trips:
        if trip.get("order_number") == order_number:
            trip["status"] = status
            trip["position"] = position
            break

    save_trips(trips)
