import csv
from datetime import datetime, timedelta, date
from collections import defaultdict

WORK_FILE = "DATA/working_hours.csv"
ROSTER_FILE = "DATA/roster.csv"

# =======================
# WORKING HOURS FUNCTIONS
# =======================

def load_working_hours():
    records = []
    try:
        with open(WORK_FILE, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                records.append(row)
    except FileNotFoundError:
        pass
    return records

def save_working_hours(records):
    fieldnames = ["date", "driver", "start_time", "end_time", "off_day", "after_hours_reason"]
    with open(WORK_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

def add_working_hour(entry):
    records = load_working_hours()
    records.append(entry)
    save_working_hours(records)

def calculate_hours(start_time, end_time):
    fmt = "%H:%M"
    start = datetime.strptime(start_time, fmt)
    end = datetime.strptime(end_time, fmt)
    if end < start:
        end += timedelta(days=1)
    return round((end - start).total_seconds() / 3600, 2)

def enrich_records(records):
    enriched = []
    for r in records:
        hours = 0
        violation = False
        after_hours = False

        if r["off_day"].lower() != "yes" and r["start_time"] and r["end_time"]:
            hours = calculate_hours(r["start_time"], r["end_time"])
            if hours > 15:
                violation = True

            # After-hours detection (outside 05:00–22:00)
            start = datetime.strptime(r["start_time"], "%H:%M").time()
            end = datetime.strptime(r["end_time"], "%H:%M").time()
            if start < datetime.strptime("05:00", "%H:%M").time() or end > datetime.strptime("22:00", "%H:%M").time():
                after_hours = True

        enriched.append({
            **r,
            "hours_worked": hours,
            "violation": violation,
            "after_hours": after_hours
        })
    return enriched

# =======================
# SUMMARY LOGIC
# =======================

def summarize_by_driver_month(records):
    summary = defaultdict(lambda: {"total_hours": 0, "days_worked": 0, "violations": 0})
    for r in records:
        if r["off_day"].lower() == "yes":
            continue
        key = (r["driver"], r["date"][:7])
        summary[key]["total_hours"] += r["hours_worked"]
        summary[key]["days_worked"] += 1
        if r["violation"]:
            summary[key]["violations"] += 1
    return summary

def group_by_year_month_driver(records):
    structure = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for r in records:
        year = r["date"][:4]
        month = r["date"][:7]
        driver = r["driver"]
        structure[year][month][driver].append(r)
    return structure

# =======================
# ROSTER MANAGEMENT
# =======================

def load_roster():
    records = []
    try:
        with open(ROSTER_FILE, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                records.append(row)
    except FileNotFoundError:
        pass
    return records

def save_roster(records):
    fieldnames = ["driver", "last_off_date", "off_cycle_days"]
    with open(ROSTER_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

def get_roster_status():
    roster = load_roster()
    today = date.today()
    status = []

    for r in roster:
        last_off = datetime.strptime(r["last_off_date"], "%Y-%m-%d").date()
        cycle = int(r.get("off_cycle_days", 7))
        next_off = last_off + timedelta(days=cycle)
        days_left = (next_off - today).days

        status.append({
            "driver": r["driver"],
            "last_off_date": r["last_off_date"],
            "off_cycle_days": cycle,
            "next_off_date": next_off.strftime("%Y-%m-%d"),
            "days_until_off": days_left,
            "status": "Due" if days_left <= 0 else "Active"
        })

    return status
