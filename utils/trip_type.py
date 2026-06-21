import pandas as pd

# Load your rates file once when the app starts
rates_df = pd.read_csv('region_rates.csv')

def calculate_allowance(trip_type, region):
    """
    Calculates total allowance based on region and trip type.
    trip_type: 'BRIDGING', 'DIRECT', or 'LOCAL'
    region: String matching the 'region' column in region_rates.csv
    """
    # Filter the dataframe for the specific region and load type
    row = rates_df[(rates_df['region'] == region.upper()) & 
                   (rates_df['load_type'] == trip_type.upper())]
    
    if not row.empty:
        base = row.iloc[0]['allowance']
        add = row.iloc[0]['additional_allowance']
        return base + add
    
    return 0 # Default if no match found



def classify_trip(row):
    loading_point = str(row.get('loading_point', '')).strip().upper()
    offloading_point = str(row.get('offloading_point', '')).strip().upper()
    delivery_note = str(row.get('delivery_note', '')).strip().upper()
    
    # 1. Check for Local Loads (Maseru origin)
    if "MASERU" in loading_point:
        if "MASERU" in offloading_point:
            return "Bridging Load"
        elif "DIRECT" in delivery_note:
            return "Direct Load"
        else:
            return "Local Load"
            
    # 2. Check for Bridging Loads (Depot to Depot)
    if "PUMA DEPOT" in offloading_point:
        return "Bridging Load"
        
    # 3. Default to Direct Load
    return "Direct Load"