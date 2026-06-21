import pandas as pd
from app import app, db, Driver

def normalize_name(raw_name):
    if not raw_name or pd.isna(raw_name):
        return "Unknown Driver"
    # Normalizes "MOEKETSI MONAHENG" to "Moeketsi Monaheng"
    parts = sorted([p.strip().capitalize() for p in str(raw_name).split()])
    return " ".join(parts)

def migrate_drivers_fix():
    csv_path = 'DATA/bto_registry.csv'
    
    try:
        # We use keep_default_na=False to prevent empty names from becoming 'NaN'
        df = pd.read_csv(csv_path, keep_default_na=False)
        # Clean column names in case there are hidden spaces around the slash
        df.columns = df.columns.str.strip()
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return

    # Using your exact header
    name_column = 'driver'

    if name_column not in df.columns:
        print(f"Error: Could not find column '{name_column}'")
        print(f"Actual columns found: {list(df.columns)}")
        return

    with app.app_context():
        print("Clearing old data from the driver table...")
        db.session.query(Driver).delete() 
        
        count = 0
        for _, row in df.iterrows():
            raw_name = row[name_column]
            if not raw_name: continue
            
            clean_name = normalize_name(raw_name)

            # Double check for duplicates before adding
            exists = Driver.query.filter_by(name=clean_name).first()
            if not exists:
                new_driver = Driver(name=clean_name)
                db.session.add(new_driver)
                count += 1
        
        db.session.commit()
        print(f"Success! Added {count} clean names to the database.")

if __name__ == "__main__":
    migrate_drivers_fix()