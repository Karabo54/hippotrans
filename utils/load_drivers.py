import csv
import os

def load_drivers():
    drivers = []
    file_path = "DATA/bto_registry.csv"
    
    # Check if file exists before trying to open it
    if not os.path.exists(file_path):
        print(f"⚠️ Warning: {file_path} not found. Returning empty list.")
        return []

    try:
        with open(file_path, newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                drivers.append(row)
    except Exception as e:
        print(f"❌ Error reading drivers.csv: {e}")
        return []
        
    return drivers