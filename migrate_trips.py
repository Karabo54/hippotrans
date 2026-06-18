import pandas as pd
import numpy as np
from datetime import datetime
from app import app, db, Trip, Driver, Vehicle

def to_py_date(val):
    """Convert pandas/numpy dates to standard Python datetime or None"""
    if pd.isna(val) or str(val).lower() in ['nat', 'nan', 'none', '', '0', '0.0']:
        return None
    try:
        if hasattr(val, 'to_pydatetime'):
            return val.to_pydatetime()
        return pd.to_datetime(val).to_pydatetime()
    except:
        return None

def safe_str(val):
    """Ensure data is a clean string or None"""
    if pd.isna(val) or str(val).lower() in ['nan', 'none', '']:
        return None
    return str(val).strip()

def safe_float(val):
    """Ensure data is a float or 0.0"""
    try:
        if pd.isna(val) or str(val).lower() in ['nan', 'none', '']:
            return 0.0
        return float(val)
    except:
        return 0.0

def migrate_trips_final():
    csv_path = 'DATA/trips.csv'
    try:
        df = pd.read_csv(csv_path)
        # Standardize headers (lowercase and stripped)
        df.columns = df.columns.str.strip().str.lower()
        
        # Remove duplicates based on order_number
        df = df.drop_duplicates(subset=['order_number'], keep='first')
        
        # Convert to standard Python objects to kill off NumPy NaN issues
        trips_data = df.replace({np.nan: None}).to_dict('records')
        print(f"Sanitized {len(trips_data)} rows. Starting migration...")
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return

    with app.app_context():
        print("Cleaning database table...")
        db.session.query(Trip).delete()
        db.session.commit()
        
        count = 0
        with db.session.no_autoflush:
            for row in trips_data:
                # Basic validation: must have an order number
                order_no = safe_str(row.get('order_number'))
                if not order_no:
                    continue

                # Database Lookups (Foreign Keys)
                did = None
                d_name = row.get('driver')
                if d_name:
                    driver_rec = Driver.query.filter(Driver.name.icontains(str(d_name))).first()
                    if driver_rec: did = int(driver_rec.id)

                vid = None
                t_reg = row.get('truck_reg')
                if t_reg:
                    veh_rec = Vehicle.query.filter_by(truck_reg=str(t_reg).upper()).first()
                    if veh_rec: vid = int(veh_rec.id)

                # Create the Trip Object following your exact header list
                new_trip = Trip(
                    # 1-4: Loading Info
                    date_loaded=to_py_date(row.get('date_loaded')),
                    loading_point=safe_str(row.get('loading_point')),
                    truck_reg=safe_str(row.get('truck_reg')),
                    trailer_reg=safe_str(row.get('trailer_reg')),
                    
                    # 5-8: Core Info
                    driver_id=did, # Linked from 'driver' column
                    customer=safe_str(row.get('customer')),
                    order_number=order_no,
                    product=safe_str(row.get('product')),
                    
                    # 9-11: Loading Metrics
                    litres_loaded=safe_float(row.get('litres_loaded')),
                    loading_km=safe_float(row.get('loading_km')),
                    loading_time=safe_str(row.get('loading_time')),
                    
                    # 12-14: Status Info
                    status=safe_str(row.get('status')),
                    position=safe_str(row.get('position')),
                    offloading_point=safe_str(row.get('offloading_point')),
                    
                    # 15-18: Offloading Info
                    date_offloaded=to_py_date(row.get('date_offloaded')),
                    litres_offloaded=safe_float(row.get('litres_offloaded')),
                    offloading_km=safe_float(row.get('offloading_km')),
                    offloading_time=safe_str(row.get('offloading_time')),
                    
                    # 19-24: Final Details
                    dn_number=safe_str(row.get('dn_number')),
                    eta=safe_str(row.get('eta')),
                    difference=safe_float(row.get('difference')),
                    km_travelled=safe_float(row.get('km_travelled')),
                    time_taken=safe_str(row.get('time_taken')),
                    allowance_status=safe_str(row.get('allowance_status')),
                    
                    # Also link the vehicle_id we looked up earlier
                    vehicle_id=vid
                )
                
                db.session.add(new_trip)
                count += 1

        try:
            db.session.commit()
            print(f"SUCCESS! All {count} rows migrated with full header mapping.")
        except Exception as e:
            print(f"Final database commit failed: {e}")
            db.session.rollback()

if __name__ == "__main__":
    migrate_trips_final()