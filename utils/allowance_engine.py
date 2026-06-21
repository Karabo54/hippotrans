import pandas as pd
import os

def get_unified_allowance_df():
    # 1. Load all three sources
    trips = pd.read_csv('DATA/trips.csv')
    puma = pd.read_csv('DATA/puma_trips.csv')
    sec = pd.read_csv('DATA/secondary_trips.csv')
    
    # 2. Add source tracking so we know which file to update later
    trips['source_file'] = 'trips.csv'
    puma['source_file'] = 'puma_trips.csv'
    sec['source_file'] = 'secondary_trips.csv'
    
    # 3. Combine
    df = pd.concat([trips, puma, sec], ignore_index=True)
    
    # 4. Load rates and regions
    rates = pd.read_csv('DATA/region_rates.csv')
    mapping = pd.read_csv('DATA/retail_to_region.csv')
    
    # 5. Classify Trip Type (Unified Logic)
    def classify_trip(row):
        load = str(row.get('loading_point', '')).upper()
        off = str(row.get('offloading_point', '')).upper()
        dn = str(row.get('delivery_note', '')).upper()
        
        if "MASERU" in load and "MASERU" in off: return "BRIDGING"
        if "MASERU" in load and "DIRECT" in dn: return "DIRECT"
        if "MASERU" in load: return "LOCAL"
        if "PUMA DEPOT" in off: return "BRIDGING"
        return "DIRECT"

    df['trip_type'] = df.apply(classify_trip, axis=1)
    
    # 6. Merge Region & Allowance
    df = pd.merge(df, mapping, on='offloading_point', how='left')
    df = pd.merge(df, rates, left_on=['region', 'trip_type'], right_on=['region', 'load_type'], how='left')
    
    # 7. Final Math
    df['food_allowance'] = df['allowance'].fillna(0) + df['additional_allowance'].fillna(0)
    df['allowance_status'] = df['allowance_status'].fillna('PENDING').str.upper()
    
    return df