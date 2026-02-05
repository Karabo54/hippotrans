import csv
from datetime import datetime, timedelta
from collections import defaultdict


FILE_PATH = "DATA/fatigue_logs.csv"


def load_working_hours():
    records = []
    try:
        with open(FILE_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                records.append(row)
    except FileNotFoundError:
        pass
    return records


def add_working_hour(entry):
    records = load_working_hours()
    records.append(entry)
    save_working_hours(records)

def delete_working_hour(index):
    records = load_working_hours()
    if 0 <= index < len(records):
        records.pop(index)
        save_working_hours(records)

def update_working_hour(index, updated_entry):
    records = load_working_hours()
    if 0 <= index < len(records):
        records[index] = updated_entry
        save_working_hours(records)

def calculate_hours(start_time, end_time):
    start = datetime.strptime(start_time, "%H:%M")
    end = datetime.strptime(end_time, "%H:%M")
    if end < start:
        end += timedelta(days=1)
    return (end - start).total_seconds() / 3600


def enrich_records(records):
    enriched = []

    for r in records:
        start = r.get("start_time") or ""
        end = r.get("end_time") or ""
        hours = 0
        violation = False
        after_hours = False

        if start and end:
            start_dt = datetime.strptime(start, "%H:%M")
            end_dt = datetime.strptime(end, "%H:%M")
            if end_dt < start_dt:
                end_dt += timedelta(days=1)
            hours = (end_dt - start_dt).seconds / 3600

            if hours > 15:
                violation = True

            if start_dt.hour < 5 or end_dt.hour >= 22:
                after_hours = True

        r["hours_worked"] = round(hours, 2)
        r["violation"] = violation
        r["after_hours"] = after_hours

        enriched.append(r)

    # 🔥 SORT BY DATE ASCENDING (oldest → newest)
    enriched.sort(key=lambda x: x["date"])

    return enriched


def group_by_year_month_driver(records):
    structure = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    for r in records:
        date_obj = datetime.strptime(r["date"], "%Y-%m-%d")
        year = str(date_obj.year)
        month = date_obj.strftime("%B")

        structure[year][month][r["driver_name"]].append(r)

    # 🔥 Sort everything
    sorted_structure = {}

    for year in sorted(structure.keys()):
        sorted_structure[year] = {}
        for month in sorted(structure[year].keys(), key=lambda m: datetime.strptime(m, "%B").month):
            sorted_structure[year][month] = {}
            for driver in sorted(structure[year][month].keys()):
                sorted_structure[year][month][driver] = structure[year][month][driver]

    return sorted_structure


def summarize_by_driver_month(records):
    summary = defaultdict(lambda: {
        "total_hours": 0,
        "days_worked": 0,
        "violations": 0,
        "after_hours": 0
    })

    for r in records:
        dt = datetime.strptime(r["date"], "%Y-%m-%d")
        driver = r["driver_name"].strip()
        month = dt.strftime("%B")  # Must match template exactly

        key = (driver, month)

        summary[key]["total_hours"] += r["hours_worked"]
        summary[key]["days_worked"] += 1
        if r["violation"]:
            summary[key]["violations"] += 1
        if r.get("after_hours"):
            summary[key]["after_hours"] += 1

    return summary

def save_working_hours(records):
    with open(FILE_PATH, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "date",
            "driver_name",
            "start_time",
            "end_time",
            "off_day",
            "after_hours_reason"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)



def summarize_by_driver_week(records):
    summary = defaultdict(lambda: defaultdict(lambda: {
        "total_hours": 0,
        "days_worked": 0,
        "violations": 0
    }))

    for r in records:
        dt = datetime.strptime(r["date"], "%Y-%m-%d")
        driver = r["driver_name"]
        month = dt.strftime("%B")
        week = dt.strftime("Week %U")

        summary[(driver, month)][week]["total_hours"] += r["hours_worked"]
        summary[(driver, month)][week]["days_worked"] += 1
        if r["violation"]:
            summary[(driver, month)][week]["violations"] += 1

    return summary

def summarize_weekly(records):
    weekly = defaultdict(lambda: defaultdict(lambda: {
        "total_hours": 0,
        "violations": 0
    }))

    for r in records:
        dt = datetime.strptime(r["date"], "%Y-%m-%d")
        year, week, _ = dt.isocalendar()
        key = f"{year}-W{week}"
        driver = r["driver_name"]
        weekly[driver][key]["total_hours"] += r["hours_worked"]
        if r["violation"]:
            weekly[driver][key]["violations"] += 1

    return weekly


def get_roster_status():
    # Placeholder for OFF rotation logic (we will enhance this next)
    return []
