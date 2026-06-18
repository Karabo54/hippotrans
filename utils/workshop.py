import csv
import os
from datetime import datetime

WORKSHOP_FILE = "DATA/workshop.csv"

def get_workshop_headers():
    """Exact headers from your requirements."""
    return [
        "JOBCARD NO.", "DATE OPENED", "DATE CLOSED", "ODO READING", "JOB REQUEST",
        "DRIVER'S NAME", "LOCATION", "MECHENIC'S NAME", "PART NUMBER/CODE",
        "PART NAME", "SIDE", "COST/PART", "QUANTITY", "CONSUMEABLES", "LABOUR",
        "TOTAL COST", "TRUCK BRAND", "TRUCK REG"
    ]

def load_workshop_data():
    """Loads all job cards. Returns empty list if file doesn't exist."""
    if not os.path.exists(WORKSHOP_FILE):
        return []
    with open(WORKSHOP_FILE, newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))

def save_job_card(data_dict):
    """
    Saves a dictionary to the workshop CSV. 
    This is used by both the Manual Form and the Breakdown Inheritance.
    """
    # 1. Calculate Total Cost
    try:
        part_cost = float(data_dict.get("COST/PART", 0) or 0)
        qty = float(data_dict.get("QUANTITY", 1) or 1)
        labour = float(data_dict.get("LABOUR", 0) or 0)
        consumables = float(data_dict.get("CONSUMEABLES", 0) or 0)
        total = (part_cost * qty) + labour + consumables
    except (ValueError, TypeError):
        total = 0

    # 2. Prepare the row based on headers
    row = {header: data_dict.get(header, "") for header in get_workshop_headers()}
    row["TOTAL COST"] = total
    
    # Generate Job Card No if missing
    if not row["JOBCARD NO."]:
        row["JOBCARD NO."] = f"JC-{datetime.now().strftime('%y%m%d%H%M')}"

    # 3. Write to CSV
    file_exists = os.path.isfile(WORKSHOP_FILE)
    with open(WORKSHOP_FILE, "a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=get_workshop_headers())
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)
    return True

def convert_breakdown_to_jobcard(breakdown_id, breakdowns_list):
    """Transforms a breakdown dict into the format expected by the workshop UI."""
    b = next((item for item in breakdowns_list if str(item.get('breakdown_id')) == str(breakdown_id)), None)
    
    if not b:
        return None

    # Map Breakdown CSV keys to the Workshop UI keys used in your HTML
    return {
        "JOBCARD NO.": f"JC-B-{b.get('breakdown_id')}",
        "DATE OPENED": b.get('reported_date'),
        "ODO READING": b.get('km_at_breakdown'),
        "JOB REQUEST": f"BREAKDOWN: {b.get('issue_description')}",
        "DRIVER'S NAME": b.get('driver'),
        "LOCATION": b.get('location'),
        "TRUCK REG": b.get('truck_reg'),
        "TRUCK BRAND": "Fleet Unit", # You can expand this if you have vehicle data
        "MECHENIC'S NAME": b.get('technician', 'TBD'),
        "status": b.get('status'),
        "breakdown_id": b.get('breakdown_id'),
        "TOTAL COST": b.get('repair_cost', '0.00'),
        "DATE CLOSED": b.get('end_date', "")
    }


# ALIAS for backward compatibility with your app.py
save_manual_job_card = save_job_card

def close_workshop_job(job_card_id, breakdown_id):
    # 1. First, mark the Job Card as Closed in workshop.csv (omitted for brevity)
    
    # 2. Update the status in breakdowns.csv
    breakdown_file = 'data/breakdowns.csv'
    temp_data = []
    
    if os.path.exists(breakdown_file):
        with open(breakdown_file, mode='r', newline='') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            for row in reader:
                # If this row matches the breakdown linked to our job card
                if row['id'] == str(breakdown_id):
                    row['status'] = 'REPAIRED'
                temp_data.append(row)

        # Write the updated data back to the file
        with open(breakdown_file, mode='w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(temp_data)

            
def save_all_workshop_data(data_list):
    """
    Overwrites the workshop.csv with a full list of jobs.
    Used when updating or closing existing job cards.
    """
    headers = get_workshop_headers()
    # Ensure the directory exists
    os.makedirs(os.path.dirname(WORKSHOP_FILE), exist_ok=True)
    
    with open(WORKSHOP_FILE, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(data_list)