import pandas as pd
from app import app, db, Vehicle
from datetime import datetime

def migrate_vehicles_full():
    csv_path = 'DATA/vehicles.csv'
    
    try:
        df = pd.read_csv(csv_path)
        df.columns = df.columns.str.strip() # Remove hidden spaces from headers
    except Exception as e:
        print(f"Error reading vehicles.csv: {e}")
        return

    print(f"Starting migration of {len(df)} vehicles...")

    with app.app_context():
        # Clear existing to start fresh and avoid unique constraint errors
        db.session.query(Vehicle).delete()
        
        count = 0
        for _, row in df.iterrows():
            reg = str(row.get('truck_reg', '')).strip().upper()
            if not reg:
                continue

            new_vehicle = Vehicle(
                truck_reg=reg,
                truck_type=row.get('truck_type'),
                truck_vin=row.get('truck_vin'),
                trailer_reg=row.get('trailer_reg'),
                trailer_type=row.get('trailer_type'),
                trailer_vin=row.get('trailer_vin'),
                pto_avail=row.get('pto_avail'),
                driver=row.get('driver'),
                status=row.get('status', 'Active'),
                
                # Handling Numbers (filling empty with 0.0)
                current_km=float(row.get('current_km', 0) or 0),
                last_service_km=float(row.get('last_service_km', 0) or 0),
                lat=float(row.get('lat', 0) or 0),
                lng=float(row.get('lng', 0) or 0),
                
                # Handling the date if it exists
                last_km_update=pd.to_datetime(row.get('last_km_update'), errors='coerce')
            )
            
            db.session.add(new_vehicle)
            count += 1
        
        db.session.commit()
        print(f"Success! Migrated {count} vehicles with all tracking and VIN data.")

if __name__ == "__main__":
    migrate_vehicles_full()