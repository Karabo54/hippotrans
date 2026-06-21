import csv
from datetime import datetime, timedelta
from collections import defaultdict
import os

FILE_PATH = "DATA/fatigue_logs.csv"


def load_working_hours():
    """Loads working hour log rows from CSV, applying default values where missing."""
    records = []
    try:
        with open(FILE_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if not row or not row.get("date"):
                    continue
                
                # Standardize missing or misaligned customer headers
                if "customer" not in row or not str(row.get("customer")).strip():
                    row["customer"] = "Other"
                    
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
    """Calculates duty lengths, logs compliance violations, and flags shift properties."""
    enriched = []

    for r in records:
        if not r.get("date"):
            continue

        start = r.get("start_time") or ""
        end = r.get("end_time") or ""
        hours = 0.0
        violation = False
        after_hours = False

        if start and end:
            try:
                start_dt = datetime.strptime(start.strip(), "%H:%M")
                end_dt = datetime.strptime(end.strip(), "%H:%M")
                if end_dt < start_dt:
                    end_dt += timedelta(days=1)
                hours = (end_dt - start_dt).seconds / 3600

                if hours > 15:
                    violation = True

                if start_dt.hour < 5 or end_dt.hour >= 22:
                    after_hours = True
            except ValueError:
                hours = 0.0

        r["hours_worked"] = round(hours, 2)
        r["violation"] = violation
        r["after_hours"] = after_hours

        # Sanitize text inputs for uniform card comparisons
        cust = str(r.get("customer") or "Other").strip().lower()
        if cust in ["engen", "puma"]:
            r["customer"] = cust.capitalize()
        else:
            r["customer"] = "Other"

        enriched.append(r)

    # Sort array chronological from oldest entry forward
    enriched.sort(key=lambda x: x.get("date", ""))
    return enriched


def load_fatigue():
    fatigue_data = []
    file_path = "DATA/fatigue.csv"
    
    if not os.path.exists(file_path):
        return []

    try:
        with open(file_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    row['hours_worked'] = float(row.get('hours_worked', 0) or 0)
                except ValueError:
                    row['hours_worked'] = 0.0
                
                fatigue_data.append(row)
    except Exception as e:
        print(f"Error loading fatigue: {e}")
        return []
        
    return fatigue_data


def _parse_date_safely(date_str):
    """Internal helper to match slash or dash date text strings safely."""
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y/%M/%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


def group_by_year_month_driver(records):
    """Nests data sets into collapsible date-tree dictionaries."""
    structure = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    for r in records:
        date_obj = _parse_date_safely(r.get("date"))
        if not date_obj:
            continue

        year = str(date_obj.year)
        month = date_obj.strftime("%B")
        driver = r.get("driver", "Unknown").strip()

        structure[year][month][driver].append(r)

    # Sort tree indices systematically
    sorted_structure = {}
    for year in sorted(structure.keys()):
        sorted_structure[year] = {}
        for month in sorted(structure[year].keys(), key=lambda m: datetime.strptime(m, "%B").month):
            sorted_structure[year][month] = {}
            for driver in sorted(structure[year][month].keys()):
                sorted_structure[year][month][driver] = sorted(
                    structure[year][month][driver], 
                    key=lambda x: x.get("date", "")
                )

    return sorted_structure


def summarize_by_driver_month(records):
    """Extracts monthly summary analytics partitioned explicitly by customer."""
    summary = defaultdict(lambda: {
        "total_hours": 0.0,
        "days_worked": 0,
        "violations": 0,
        "after_hours": 0,
        "engen_hours": 0.0,
        "engen_days": 0,
        "puma_hours": 0.0,
        "puma_days": 0,
        "other_hours": 0.0,
        "other_days": 0
    })

    for r in records:
        dt = _parse_date_safely(r.get("date"))
        if not dt:
            continue

        driver = r.get("driver", "Unknown").strip()
        month = dt.strftime("%B")
        key = (driver, month)

        hours = float(r.get("hours_worked", 0) or 0)
        is_off = str(r.get("off_day", "no")).lower() == "yes"
        cust = str(r.get("customer", "Other")).lower().strip()

        # Update absolute aggregates
        summary[key]["total_hours"] = round(summary[key]["total_hours"] + hours, 2)
        if not is_off:
            summary[key]["days_worked"] += 1

        if r.get("violation"):
            summary[key]["violations"] += 1
        if r.get("after_hours"):
            summary[key]["after_hours"] += 1

        # Calculate customer allocations
        if cust == "engen":
            summary[key]["engen_hours"] = round(summary[key]["engen_hours"] + hours, 2)
            if not is_off:
                summary[key]["engen_days"] += 1
        elif cust == "puma":
            summary[key]["puma_hours"] = round(summary[key]["puma_hours"] + hours, 2)
            if not is_off:
                summary[key]["puma_days"] += 1
        else:
            summary[key]["other_hours"] = round(summary[key]["other_hours"] + hours, 2)
            if not is_off:
                summary[key]["other_days"] += 1

    return summary


def save_working_hours(records):
    """Saves records safely down to the structured CSV persistence schema."""
    os.makedirs(os.path.dirname(FILE_PATH), exist_ok=True)
    with open(FILE_PATH, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "date",
            "driver",
            "customer",
            "start_time",
            "end_time",
            "off_day",
            "after_hours_reason"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for r in records:
            writer.writerow({
                "date": r.get("date"),
                "driver": r.get("driver"),
                "customer": r.get("customer", "Other"),
                "start_time": r.get("start_time"),
                "end_time": r.get("end_time"),
                "off_day": r.get("off_day", "no"),
                "after_hours_reason": r.get("after_hours_reason", "")
            })


def summarize_by_driver_week(records):
    """Groups hourly logs into localized calendar week blocks per customer."""
    summary = defaultdict(lambda: defaultdict(lambda: {
        "total_hours": 0.0,
        "days_worked": 0,
        "violations": 0,
        "engen_hours": 0.0,
        "puma_hours": 0.0,
        "other_hours": 0.0
    }))

    for r in records:
        dt = _parse_date_safely(r.get("date"))
        if not dt:
            continue

        try:
            driver = r["driver"]
            month = dt.strftime("%B")
            week = dt.strftime("Week %U")

            key = (driver, month)
            hours = float(r.get("hours_worked", 0) or 0)
            is_off = str(r.get("off_day", "no")).lower() == "yes"
            cust = str(r.get("customer", "Other")).lower().strip()

            summary[key][week]["total_hours"] = round(summary[key][week]["total_hours"] + hours, 2)
            if not is_off:
                summary[key][week]["days_worked"] += 1
                
            if r.get("violation"):
                summary[key][week]["violations"] += 1

            # Apportion week breakdowns
            if cust == "engen":
                summary[key][week]["engen_hours"] = round(summary[key][week]["engen_hours"] + hours, 2)
            elif cust == "puma":
                summary[key][week]["puma_hours"] = round(summary[key][week]["puma_hours"] + hours, 2)
            else:
                summary[key][week]["other_hours"] = round(summary[key][week]["other_hours"] + hours, 2)

        except KeyError:
            continue

    return summary


def summarize_weekly(records):
    weekly = defaultdict(lambda: defaultdict(lambda: {
        "total_hours": 0.0,
        "violations": 0
    }))

    for r in records:
        dt = _parse_date_safely(r.get("date"))
        if not dt:
            continue
            
        year, week, _ = dt.isocalendar()
        key = f"{year}-W{week}"
        driver = r["driver"]
        
        hours = float(r.get("hours_worked", 0) or 0)
        weekly[driver][key]["total_hours"] = round(weekly[driver][key]["total_hours"] + hours, 2)
        if r.get("violation"):
            weekly[driver][key]["violations"] += 1

    return weekly


def get_roster_status():
    return []

def calculate_monthly_customer_totals(enriched_records):
    """Calculates fleet-wide customer totals broken down by individual Year and Month."""
    # Structure: structure[year][month] = { customer_metrics... }
    monthly_totals = defaultdict(
        lambda: defaultdict(
            lambda: {
                "engen_hours": 0.0,
                "engen_days": 0,
                "puma_hours": 0.0,
                "puma_days": 0,
                "other_hours": 0.0,
                "other_days": 0,
            }
        )
    )

    for r in enriched_records:
        dt = _parse_date_safely(r.get("date"))
        if not dt:
            continue

        year = str(dt.year)
        month = dt.strftime("%B")  # e.g., "May"

        hours = float(r.get("hours_worked", 0) or 0)
        is_off = str(r.get("off_day", "no")).lower() == "yes"
        cust = str(r.get("customer", "Other")).lower().strip()

        if cust == "engen":
            monthly_totals[year][month]["engen_hours"] += hours
            if not is_off:
                monthly_totals[year][month]["engen_days"] += 1
        elif cust == "puma":
            monthly_totals[year][month]["puma_hours"] += hours
            if not is_off:
                monthly_totals[year][month]["puma_days"] += 1
        else:
            monthly_totals[year][month]["other_hours"] += hours
            if not is_off:
                monthly_totals[year][month]["other_days"] += 1

    # Round floating-point values for clean presentation
    for year in monthly_totals:
        for month in monthly_totals[year]:
            monthly_totals[year][month]["engen_hours"] = round(
                monthly_totals[year][month]["engen_hours"], 2
            )
            monthly_totals[year][month]["puma_hours"] = round(
                monthly_totals[year][month]["puma_hours"], 2
            )
            monthly_totals[year][month]["other_hours"] = round(
                monthly_totals[year][month]["other_hours"], 2
            )

    return monthly_totals

def calculate_global_customer_totals(enriched_records):
    """Calculates the combined grand totals across all drivers for each customer."""
    totals = {
        "engen_hours": 0.0,
        "engen_days": 0,
        "puma_hours": 0.0,
        "puma_days": 0,
        "other_hours": 0.0,
        "other_days": 0,
    }

    for r in enriched_records:
        hours = float(r.get("hours_worked", 0) or 0)
        is_off = str(r.get("off_day", "no")).lower() == "yes"
        cust = str(r.get("customer", "Other")).lower().strip()

        if cust == "engen":
            totals["engen_hours"] += hours
            if not is_off:
                totals["engen_days"] += 1
        elif cust == "puma":
            totals["puma_hours"] += hours
            if not is_off:
                totals["puma_days"] += 1
        else:
            totals["other_hours"] += hours
            if not is_off:
                totals["other_days"] += 1

    # Round hours to 2 decimal places cleanly
    totals["engen_hours"] = round(totals["engen_hours"], 2)
    totals["puma_hours"] = round(totals["puma_hours"], 2)
    totals["other_hours"] = round(totals["other_hours"], 2)

    return totals

def get_registry_drivers():
    """Fetches all active driver records from DATA/bto_registry.csv dynamically."""
    drivers = []
    registry_path = 'DATA/bto_registry.csv' 
    
    if not os.path.exists(registry_path):
        return []

    with open(registry_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('TYPE') == 'DRIVER' or not row.get('TYPE'):
                name = row.get('driver', 'Unknown')
                if name:
                    drivers.append({'driver': name})
    
    return sorted(drivers, key=lambda x: x['driver'])