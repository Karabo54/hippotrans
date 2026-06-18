import csv
import os

def load_incidents():
    incidents = []
    # Use the path defined in your app (usually DATA/incidents.csv)
    file_path = "DATA/incidents.csv"
    
    if not os.path.exists(file_path):
        return []

    try:
        with open(file_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Basic data cleanup
                incidents.append(row)
    except Exception as e:
        print(f"Error loading incidents: {e}")
        return []
        
    return incidents