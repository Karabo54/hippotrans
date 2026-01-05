import csv
from datetime import datetime

# Path to your vehicles CSV
csv_file = "data/vehicles.csv"

with open(csv_file, newline="") as file:
    reader = csv.DictReader(file)
    
    print("VEHICLE REGISTER")
    print("-" * 60)
    
    for row in reader:
        vehicle_id = row["vehicle_id"]
        reg = row["registration"]
        roadworthy_expiry = row["roadworthy_expiry"]
        dg_expiry = row["dg_expiry"]
        status = row["status"]
        
        # Convert dates to datetime
        roadworthy_date = datetime.strptime(roadworthy_expiry, "%Y-%m-%d")
        dg_date = datetime.strptime(dg_expiry, "%Y-%m-%d")
        today = datetime.today()
        
        # Simple compliance check
        if roadworthy_date < today or dg_date < today:
            status = "LOCKED"
        
        print(f"{vehicle_id} | {reg} | Roadworthy: {roadworthy_expiry} | DG: {dg_expiry} | STATUS: {status}")
