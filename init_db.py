import sqlite3
import pandas as pd
import glob
import os

def build_database():
    conn = sqlite3.connect('fleet.db')
    csv_files = glob.glob("DATA/*.csv")
    
    if not csv_files:
        print("❌ No CSV files found in the DATA folder!")
        return

    for file_path in csv_files:
        table_name = os.path.splitext(os.path.basename(file_path))[0]
        
        # --- NEW SAFETY CHECK ---
        # Check if file size is 0 or if it's empty
        if os.path.getsize(file_path) == 0:
            print(f"⚠️ Skipping '{table_name}': File is empty.")
            continue
            
        try:
            df = pd.read_csv(file_path)
            
            # Double check if the DataFrame itself is empty
            if df.empty:
                print(f"⚠️ Skipping '{table_name}': No data found in CSV.")
                continue

            df = df.drop_duplicates()
            df.to_sql(table_name, conn, if_exists='replace', index=False)
            print(f"✅ Created table: {table_name} ({len(df)} rows)")
            
        except pd.errors.EmptyDataError:
            print(f"⚠️ Skipping '{table_name}': EmptyDataError (no columns to parse).")
        except Exception as e:
            print(f"❌ Error processing '{table_name}': {e}")

    conn.close()
    print("\n🚀 SUCCESS: 'fleet.db' is updated!")

if __name__ == "__main__":
    build_database()