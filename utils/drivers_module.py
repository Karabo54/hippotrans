import pandas as pd
import os
from datetime import datetime, timedelta

DATA_FILE = 'data/bto_registry.csv'

def get_bto_registry():
    if not os.path.exists('data'):
        os.makedirs('data')
        
    # EXACT HEADERS matching your requirement
    cols = [
        'bto_id', 'driver', 'DOB', 'ID NO', 'AGE', 'Medical Condition', 
        'Drivers License Exp Date', 'PDrP Exp Date', 'International Driving Permit -Exp Date', 
        'Defensive Driving- Exp Date', 'Smith System Expiry Date', 'Medical Exp Date', 
        'Loadind and Offloading procedure', 'In Cab Assessment K53', 'In Cab Assessment K53 Expiry Date', 
        'Spill Kit Training', 'Tanker Roll-Over Prevention', 'Customer Care', 
        'Environmental Awareness', 'Truck and Defects Check List', 'ZETO', 
        'Hazchem / Dangerous Goods', 'Fire Fighting', 'First Aid', 'Induction'
    ]

    if not os.path.exists(DATA_FILE):
        pd.DataFrame(columns=cols).to_csv(DATA_FILE, index=False)
    
    # Force read as string to prevent ID errors
    df = pd.read_csv(DATA_FILE, dtype=str).fillna('')
    today = datetime.now()
    
    def get_status(date_str):
        if not date_str or date_str == '' or date_str == 'nan': return 'valid'
        try:
            exp = datetime.strptime(str(date_str), '%Y-%m-%d')
            if exp < today: return 'expired'
            if exp < (today + timedelta(days=30)): return 'warning'
        except: pass
        return 'valid'

    # MAPPING LOGIC TO CSV HEADERS
    df['pdp_status'] = df['PDrP Exp Date'].apply(get_status)
    df['med_status'] = df['Medical Exp Date'].apply(get_status)
    df['haz_status'] = df['Hazchem / Dangerous Goods'].apply(get_status)
    return df
def get_bto_stats(df):
    today = datetime.now()
    total_expired = 0
    total_due = 0
    
    date_cols = [col for col in df.columns if 'Date' in col or 'Exp' in col or 'procedure' in col]

    for _, row in df.iterrows():
        for col in date_cols:
            val = row.get(col, '')
            if val and val != '' and val != 'nan':
                try:
                    exp = datetime.strptime(str(val), '%Y-%m-%d')
                    days_left = (exp - today).days
                    
                    if days_left < 0:
                        # This will now catch Karabo's 2025-12-09 date
                        total_expired += 1
                    elif 0 <= days_left <= 30:
                        total_due += 1
                except:
                    continue

    return {
        "top": {
            "total": len(df),
            "expired": total_expired,
            "due": total_due
        }
    }

def delete_bto_entry(bto_id):
    df = pd.read_csv(DATA_FILE, dtype=str).fillna('')
    df = df[df['bto_id'].astype(str) != str(bto_id)]
    df.to_csv(DATA_FILE, index=False)