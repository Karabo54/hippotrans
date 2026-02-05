import csv
import os
from datetime import datetime
from logic.vehicles import load_vehicles, save_vehicles

BREAKDOWNS_FILE = "DATA/breakdowns.csv"


def load_breakdowns():
    if not os.path.exists(BREAKDOWNS_FILE):
        return []
    with open(BREAKDOWNS_FILE, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_breakdowns(breakdowns):
    if not breakdowns:
        return

    fieldnames = breakdowns[0].keys()  # This ensures all fields (including status) are saved

    with open(BREAKDOWNS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(breakdowns)


def add_breakdown(form):
    breakdowns = load_breakdowns()
    breakdown_id = f"BD{len(breakdowns)+1:05d}"

    new_entry = {
        "breakdown_id": breakdown_id,
        "truck_reg": form.get("truck_reg"),
        "driver": form.get("driver"),
        "location": form.get("location"),
        "issue_description": form.get("issue_description"),
        "reported_date": form.get("reported_date"),
        "reported_time": form.get("reported_time"),
        "km_at_breakdown": form.get("km_at_breakdown"),
        "status": "REPORTED",
        "repair_start_date": "",
        "repair_end_date": "",
        "downtime_hours": "",
        "repair_cost": "",
        "workshop": "",
        "notes": ""
    }

    breakdowns.append(new_entry)
    save_breakdowns(breakdowns)

    # Mark vehicle unavailable
    mark_vehicle_unavailable(new_entry["truck_reg"])

    return True


def update_breakdown_status(breakdown_id, status, repair_cost=None, workshop=None, notes=None):
    breakdowns = load_breakdowns()
    for b in breakdowns:
        if b["breakdown_id"] == breakdown_id:
            b["status"] = status
            now = datetime.now().strftime("%Y-%m-%d %H:%M")

            if status == "IN REPAIR":
                b["repair_start_date"] = now

            if status == "REPAIRED":
                b["repair_end_date"] = now
                b["repair_cost"] = repair_cost or ""
                b["workshop"] = workshop or ""
                b["notes"] = notes or ""
                b["downtime_hours"] = calculate_downtime(b)

                # Mark vehicle available again
                mark_vehicle_available(b["truck_reg"])

    save_breakdowns(breakdowns)


def calculate_downtime(breakdown):
    try:
        start = datetime.strptime(
            breakdown["reported_date"] + " " + breakdown["reported_time"], "%Y-%m-%d %H:%M"
        )
        end = datetime.strptime(breakdown["repair_end_date"], "%Y-%m-%d %H:%M")
        diff = end - start
        hours = round(diff.total_seconds() / 3600, 2)
        return str(hours)
    except:
        return ""


def mark_vehicle_unavailable(truck_reg):
    vehicles = load_vehicles()
    for v in vehicles:
        if v.get("truck_reg") == truck_reg:
            v["status"] = "BREAKDOWN"
    save_vehicles(vehicles)


def mark_vehicle_available(truck_reg):
    vehicles = load_vehicles()
    for v in vehicles:
        if v.get("truck_reg") == truck_reg:
            v["status"] = "AVAILABLE"
    save_vehicles(vehicles)
