import csv
import os
from datetime import datetime, timedelta

KM_FILE = "DATA/km_readings.csv"

def ensure_km_file():
    if not os.path.exists(KM_FILE):
        with open(KM_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "reg_number",
                "reading_date",
                "km_reading"
            ])

def load_km_readings():
    ensure_km_file()
    readings = []
    with open(KM_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            readings.append(row)
    return readings

def get_last_km_update(reg_number):
    readings = load_km_readings()
    vehicle_readings = [r for r in readings if r["reg_number"] == reg_number]

    if not vehicle_readings:
        return None

    latest = max(vehicle_readings, key=lambda r: r["reading_date"])
    return latest

def add_km_reading(reg_number, km_reading, reading_date=None):
    if reading_date is None:
        reading_date = datetime.now().strftime("%Y-%m-%d")

    with open(KM_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([reg_number, reading_date, km_reading])

def is_km_update_required(reg_number):
    """
    Returns True if the vehicle does NOT have a KM reading
    for the current week (Monday–Sunday).
    """
    last = get_last_km_update(reg_number)
    if not last:
        return True

    last_date = datetime.strptime(last["reading_date"], "%Y-%m-%d").date()
    today = datetime.now().date()

    # Get this week's Monday
    this_monday = today - timedelta(days=today.weekday())

    return last_date < this_monday
