import pandas as pd
import time
import random
import os

# Path to your file
CSV_FILE = os.path.join('DATA', 'vehicles.csv') 
MOVE_AMOUNT = 0.008        
UPDATE_INTERVAL = 5        

def simulate_movement():
    print(f"🚀 GPS Simulation Started. Updating {CSV_FILE} every {UPDATE_INTERVAL}s...")
    
    while True:
        try:
            if not os.path.exists(CSV_FILE):
                print(f"❌ Error: Cannot find {CSV_FILE}")
                time.sleep(10)
                continue

            # Load the CSV
            df = pd.read_csv(CSV_FILE)
            
            # Use .empty to check if there is data (Fixes your specific error)
            if not df.empty:
                # Pick a random row index from the available ones
                idx = random.choice(df.index.tolist())
                
                # Update lat/lng with a tiny random movement
                # We use .at to update the specific cell
                df.at[idx, 'lat'] = float(df.at[idx, 'lat']) + random.uniform(-MOVE_AMOUNT, MOVE_AMOUNT)
                df.at[idx, 'lng'] = float(df.at[idx, 'lng']) + random.uniform(-MOVE_AMOUNT, MOVE_AMOUNT)
                
                # Save back to CSV without the index row
                df.to_csv(CSV_FILE, index=False)
                
                reg = df.at[idx, 'truck_reg']
                print(f"✅ Moved Unit {reg} to {df.at[idx, 'lat']:.4f}, {df.at[idx, 'lng']:.4f}")
            else:
                print("⚠️ CSV is empty. Waiting...")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            
        time.sleep(UPDATE_INTERVAL)

if __name__ == "__main__":
    simulate_movement()