import csv
from datetime import datetime, timedelta

def get_compliance_data():
    fleet_data = []
    summary = {"expired": 0, "due_30": 0, "due_60": 0}
    today = datetime.now()

    with open('data/compliance.csv', mode='r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            expiry = datetime.strptime(row['expiry_date'], '%Y-%m-%d')
            diff = (expiry - today).days

            if diff < 0:
                row['status'] = "EXPIRED"
                summary['expired'] += 1
            elif diff <= 30:
                row['status'] = "DUE-30"
                summary['due_30'] += 1
            elif diff <= 60:
                row['status'] = "DUE-60"
                summary['due_60'] += 1
            else:
                row['status'] = "VALID"
            
            fleet_data.append(row)
            
    return fleet_data, summary