import csv
import os
import uuid
import json
from collections import defaultdict


# Use consistent paths
FUEL_FILE = "DATA/fuel.csv"
TRIPS_FILE = "DATA/trips.csv"
PRICE_PER_LITRE = 19.00

def load_fuel():
    """Efficiently load fuel logs from CSV."""
    if not os.path.exists(FUEL_FILE):
        return []
    with open(FUEL_FILE, newline="", encoding="utf-8") as f:
        # Converting to list immediately for sorting/processing
        return list(csv.DictReader(f))

def save_fuel(logs):
    """Save logs with a consistent header order."""
    os.makedirs(os.path.dirname(FUEL_FILE), exist_ok=True)
    fieldnames = ["id", "order_number", "date", "truck_reg", "driver", 
                  "litres", "km_at_fuel", "cost", "route", "customer", "duplicate_reason"]
    with open(FUEL_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(logs)
def analyze_fuel_intelligence():
    """
    STRICT AUDIT & EFFICIENCY ENGINE
    Formula: [ Litres / (Current KM - Previous KM) ] * 100
    """
    # 1. Load data
    logs = []
    if os.path.exists(FUEL_FILE):
        with open(FUEL_FILE, newline="", encoding="utf-8") as f:
            logs = list(csv.DictReader(f))
    
    trip_data_map = {}
    if os.path.exists(TRIPS_FILE):
        with open(TRIPS_FILE, newline="", encoding="utf-8") as f:
            all_trips = list(csv.DictReader(f))
            for t in all_trips:
                ord_no = str(t.get('order_number', '')).strip()
                if ord_no:
                    trip_data_map[ord_no] = {
                        'skip_reason': t.get('fuel_skip_reason', '').strip(),
                        'details': t
                    }

    # 2. Sort logs by Truck and Odometer
    try:
        logs.sort(key=lambda x: (x['truck_reg'], float(x.get('km_at_fuel', 0) or 0)))
    except:
        pass

    # 3. Initialize Stats Containers
    stats = {
        'total_spend': 0, 
        'total_litres': 0,
        'trucks': defaultdict(lambda: {'litres': 0, 'km': 0, 'efficiency': 0, 'missed': 0, 'rating': 'N/A'}),
        'drivers': defaultdict(lambda: {'litres': 0, 'km': 0, 'efficiency': 0}),
        'alerts': [],
        'missing_logs': [] 
    }

    # previous_log now stores: { 'truck_reg': {'km': 123, 'date': '...', 'driver': '...'} }
    previous_log = {} 
    fueled_order_numbers = set()

    # 4. Process Every Fuel Log
    for log in logs:
        reg = log.get('truck_reg')
        driver_name = log.get('driver', 'Unknown')
        litres = float(log.get('litres') or 0)
        km_curr = float(log.get('km_at_fuel') or 0)
        curr_date = log.get('date') or log.get('date_loaded')
        ord_no = str(log.get('order_number', '')).strip()
        cost = float(log.get('cost') or (litres * PRICE_PER_LITRE))
        
        if ord_no: 
            fueled_order_numbers.add(ord_no)
        
        # --- THE L/100km FORMULA & GAP DETECTION ---
        if reg in previous_log and litres > 0:
            prev_data = previous_log[reg]
            dist_since_last_fill = km_curr - prev_data['km']
            
            if dist_since_last_fill > 0:
                # Log-specific L/100km
                log['calculated_efficiency'] = round((litres / dist_since_last_fill) * 100, 1)
                
                # Accumulate Stats
                stats['trucks'][reg]['km'] += dist_since_last_fill
                stats['trucks'][reg]['litres'] += litres
                stats['drivers'][driver_name]['km'] += dist_since_last_fill
                stats['drivers'][driver_name]['litres'] += litres
                
                # Odometer Gap Detection (Alerts)
                if dist_since_last_fill > 2500:
                    stats['trucks'][reg]['missed'] += 1
                    stats['alerts'].append({
                        'truck_reg': reg,
                        'km_gap': int(dist_since_last_fill),
                        'start_date': prev_data['date'], # From previous log
                        'end_date': curr_date,           # From current log
                        'prev_driver': prev_data['driver'],
                        'next_driver': driver_name
                    })
            else:
                log['calculated_efficiency'] = None
        else:
            log['calculated_efficiency'] = None

        # Update Totals and "Previous" reference for next iteration
        stats['total_litres'] += litres
        stats['total_spend'] += cost
        previous_log[reg] = {
            'km': km_curr,
            'date': curr_date,
            'driver': driver_name
        }

    # 5. Finalize Averages
    for reg, data in stats['trucks'].items():
        if data['km'] > 0:
            data['efficiency'] = round((data['litres'] / data['km']) * 100, 1)
            if data['efficiency'] < 38 and data['missed'] == 0: data['rating'] = "⭐⭐⭐⭐⭐"
            elif data['efficiency'] < 48: data['rating'] = "⭐⭐⭐"
            else: data['rating'] = "⭐"

    for drv, data in stats['drivers'].items():
        if data['km'] > 0:
            data['efficiency'] = round((data['litres'] / data['km']) * 100, 1)

    # 6. STRICT AUDIT: Detect Trips missing Fuel Entries
    for ord_no, data in trip_data_map.items():
        if ord_no not in fueled_order_numbers and not data['skip_reason']:
            t = data['details']
            stats['missing_logs'].append({
                'order_number': ord_no,
                'date': t.get('date_loaded'),
                'truck': t.get('truck_reg'),
                'driver': t.get('driver'),
                'route': t.get('offloading_point')
            })

    return stats, logs

def add_fuel_entry(form_data):
    """Adds a single entry and handles the auto-ID generation."""
    logs = load_fuel()
    
    # Ensure numerical data is clean
    litres = form_data.get("litres") or 0
    cost = form_data.get("cost")
    if not cost and litres:
        cost = float(litres) * PRICE_PER_LITRE

    new_entry = {
        "id": str(uuid.uuid4())[:8],
        "order_number": form_data.get("order_number"),
        "date": form_data.get("date"),
        "truck_reg": form_data.get("truck_reg"),
        "driver": form_data.get("driver"),
        "litres": litres,
        "km_at_fuel": form_data.get("km_at_fuel"),
        "cost": cost,
        "route": form_data.get("route", ""),
        "customer": form_data.get("customer", ""),
        "duplicate_reason": form_data.get("duplicate_reason", "")
    }
    logs.append(new_entry)
    save_fuel(logs)
    return True

def load_unassigned_trips():
    """SPEED BOOST: Filters unassigned trips in Python, not in HTML."""
    if not os.path.exists(TRIPS_FILE):
        return [], [] # Return two empty lists
        
    with open(TRIPS_FILE, newline="", encoding="utf-8") as f:
        trips = list(csv.DictReader(f))
    
    fuel_logs = load_fuel()
    # Create a 'set' for lightning-fast comparison
    fueled_orders = {str(log.get('order_number')) for log in fuel_logs if log.get('order_number') and not log.get('duplicate_reason')}
    
    # Filter list: trips that haven't been fueled yet
    unassigned = [t for t in trips if str(t.get('order_number')) not in fueled_orders]
    
    # FIX: Return unassigned (list) AND trips (list)
    return unassigned, trips

# Add these at the very bottom of fuel_logic.py
def fuel_consumption_stats():
    """Alias for the new intelligence function to fix ImportErrors"""
    return analyze_fuel_intelligence()

def analyze_fuel_health():
    """Alias for alerts to fix ImportErrors"""
    data = analyze_fuel_intelligence()
    return data['alerts']