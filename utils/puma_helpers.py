import pandas as pd
import os

# Define the absolute path to your DATA folder
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Updated simplified file paths
PUMA_PLAN_CSV = os.path.join(BASE_DIR, 'DATA', 'puma_plan.csv')
PUMA_TRIPS_CSV = os.path.join(BASE_DIR, 'DATA', 'puma_trips.csv')

def get_puma_summary():
    """Reads the Loading Plan and returns stats for the top cards."""
    try:
        df = pd.read_csv(PUMA_PLAN_CSV)
        # Drop rows where 'Planned' is NaN to find the last valid entry
        df_valid = df.dropna(subset=['Planned '])
        if not df_valid.empty:
            latest = df_valid.iloc[-1]
            return {
                'planned': latest['Planned '],
                'actual': latest['Actual Loaded'],
                'variance': latest['Under/Over']
            }
    except Exception:
        pass
    return {'planned': 0, 'actual': 0, 'variance': 0}

def get_puma_active_trips():
    import pandas as pd
    # Use the constant we set: DATA/puma_trips.csv
    filepath = PUMA_TRIPS_CSV 
    
    if not os.path.exists(filepath):
        return []
    
    try:
        # 1. Read the CSV
        df = pd.read_csv(filepath)
        
        # 2. Convert all column names to lowercase just in case
        df.columns = [c.lower().replace(' ', '_') for c in df.columns]
        
        # 3. Clean up the data (remove NaN)
        df = df.fillna('')
        
        # 4. Return as list of dicts
        return df.to_dict(orient='records')
    except Exception as e:
        print(f"Error reading puma_trips.csv: {e}")
        return []