import csv
from datetime import datetime

# Path to your drivers CSV
csv_file = "data/drivers.csv"

# Open the CSV file
with open(csv_file, newline="") as file:
    reader = csv.DictReader(file)
    
    print("DRIVER REGISTER")
    print("-" * 50)
    
    # Loop through each driver
    for row in reader:
        driver_id = row["driver_id"]
        name = row["full_name"]
        pdp_expiry = row["pdp_expiry"]
        medical_expiry = row["medical_expiry"]
        status = row["status"]
        
        # Check PDP expiry
        pdp_date = datetime.strptime(pdp_expiry, "%Y-%m-%d")
        medical_date = datetime.strptime(medical_expiry, "%Y-%m-%d")
        today = datetime.today()
        
        # Simple compliance check
        if pdp_date < today or medical_date < today:
            status = "SUSPENDED"
        
        print(f"{driver_id} | {name} | PDP: {pdp_expiry} | MEDICAL: {medical_expiry} | STATUS: {status}")
