import csv
import os
from datetime import datetime, date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_PATH = os.path.join(BASE_DIR, "..", "DATA", "compliance.csv")


def load_compliance():
    print("🟢 Loading compliance file from:", FILE_PATH)

    records = []

    if not os.path.exists(FILE_PATH):
        print("❌ FILE NOT FOUND:", FILE_PATH)
        return records

    with open(FILE_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)

    print("🟢 Loaded records:", records)
    return records


def calculate_status(doc_type, expiry_date_str):
    today = date.today()
    expiry_date = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
    days_remaining = (expiry_date - today).days

    warning_days = 50 if doc_type == "Meter Calibration Certificate" else 30

    if days_remaining < 0:
        status = "Expired"
        color = "red"
    elif days_remaining <= warning_days:
        status = "Almost Due"
        color = "orange"
    else:
        status = "Valid"
        color = "green"

    return status, days_remaining, color


def enrich_compliance_records(records):
    enriched = []
    for r in records:
        status, days_remaining, color = calculate_status(r["doc_type"], r["expiry_date"])
        r["status"] = status
        r["days_remaining"] = days_remaining
        r["color"] = color
        enriched.append(r)
    return enriched


def get_current_month_expiries(records):
    today = date.today()
    expiring = []

    for r in records:
        expiry = datetime.strptime(r["expiry_date"], "%Y-%m-%d").date()
        if expiry.month == today.month and expiry.year == today.year:
            status, days_remaining, color = calculate_status(r["doc_type"], r["expiry_date"])
            r["status"] = status
            r["days_remaining"] = days_remaining
            r["color"] = color
            expiring.append(r)

    return expiring
