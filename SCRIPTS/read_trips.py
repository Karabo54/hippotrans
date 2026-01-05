import csv

csv_file = "data/fuel_trips.csv"

with open(csv_file, newline="") as file:
    reader = csv.DictReader(file)
    
    print("FUEL TRIPS REGISTER")
    print("-" * 70)
    
    for row in reader:
        print(f"{row['trip_id']} | {row['date']} | Truck: {row['truck_id']} | Driver: {row['driver_id']} | Fuel: {row['fuel_type']} | Qty: {row['quantity_liters']}L | {row['origin']} -> {row['destination']} | Status: {row['status']}")
