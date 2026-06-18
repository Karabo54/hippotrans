import pandas as pd
from datetime import datetime

def get_finance_data(df):
    """Filters trips for Finance and calculates totals."""
    # Finance only cares about OFFLOADED trips
    ready_to_bill = df[df['status'] == 'OFFLOADED'].copy()
    
    # Ensure numeric types for calculation
    ready_to_bill['litres_offloaded'] = pd.to_numeric(ready_to_bill['litres_offloaded'], errors='coerce').fillna(0)
    
    # Example Rate Logic: R2.15 per litre (Adjust this to your actual rates)
    rate = 2.15 
    ready_to_bill['amount'] = ready_to_bill['litres_offloaded'] * rate
    
    # Group by Customer for the Finance Summary Cards
    summary = ready_to_bill.groupby('customer').agg({
        'order_number': 'count',
        'amount': 'sum'
    }).to_dict(orient='index')
    
    return ready_to_bill, summary