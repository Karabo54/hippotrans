import os
import pandas as pd
from datetime import datetime

def get_current_cycle_window():
    """
    Computes the operational payroll/reporting window from the 17th to the 16th.
    """
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if today.day >= 17:
        start_date = today.replace(day=17)
        if today.month == 12:
            end_date = today.replace(year=today.year + 1, month=1, day=16)
        else:
            end_date = today.replace(month=today.month + 1, day=16)
    else:
        if today.month == 1:
            start_date = today.replace(year=today.year - 1, month=12, day=17)
        else:
            start_date = today.replace(month=today.month - 1, day=17)
        end_date = today.replace(day=16)
        
    return start_date, end_date

def calculate_cycle_days_home(date_off_taken, start_cycle, end_cycle):
    """
    Calculates how many days a driver spent at home exclusively within the 17th-16th window.
    """
    if pd.isnull(date_off_taken):
        return 0
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    actual_start = max(date_off_taken.replace(tzinfo=None), start_cycle)
    actual_end = min(today, end_cycle)
    
    if actual_start > actual_end:
        return 0
    return max(0, (actual_end - actual_start).days)

def normalize_driver(name):
    """
    Normalizes names to fix string matching bugs (e.g. Ts'ilo vs Tsilo).
    """
    if pd.isnull(name):
        return ""
    return str(name).strip().lower().replace("'", "").replace("`", "").replace(" ", "")

def process_advanced_roster_data():
    roster_csv = os.path.join('DATA', 'roster.csv')
    registry_csv = os.path.join('DATA', 'bto_registry.csv')
    rates_csv = os.path.join('DATA', 'trip_rates.csv')
    
    # Active operational logs
    puma_csv = os.path.join('DATA', 'puma_trips.csv')
    secondary_csv = os.path.join('DATA', 'secondary_trips.csv')
    trips_csv = os.path.join('DATA', 'trips.csv')

    df_roster = pd.read_csv(roster_csv).fillna('') if os.path.exists(roster_csv) else pd.DataFrame()
    df_registry = pd.read_csv(registry_csv).fillna('') if os.path.exists(registry_csv) else pd.DataFrame()
    df_rates = pd.read_csv(rates_csv).fillna('') if os.path.exists(rates_csv) else pd.DataFrame()

    # Dynamic adaptation to your actual CSV header structure
    registry_name_col = None
    if not df_registry.empty:
        if 'driver' in df_registry.columns:
            registry_name_col = 'driver'
        elif 'driver' in df_registry.columns:
            registry_name_col = 'driver'

    if df_registry.empty or not registry_name_col:
        return [], {'ratio_status': 'UNKNOWN', 'msg': 'Driver column not found in bto_registry.csv.'}

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_cycle, end_cycle = get_current_cycle_window()

    if not df_roster.empty:
        df_roster['date_truck_taken'] = pd.to_datetime(df_roster['date_truck_taken'], errors='coerce')
        df_roster['date_off_taken'] = pd.to_datetime(df_roster['date_off_taken'], errors='coerce')
    
    # Build custom trip key maps
    rates_map = {}
    if not df_rates.empty:
        for _, r in df_rates.iterrows():
            key = (str(r.get('loading_point', '')).strip().upper(), str(r.get('offloading_point', '')).strip().upper())
            rates_map[key] = float(r.get('base_weight', 1.0))

    # Initialize weights tracking using the correctly mapped master registry rows
    driver_weighted_loads = {}
    normalized_registry_map = {}
    
    for _, row in df_registry.iterrows():
        orig_name = str(row[registry_name_col]).strip()
        if not orig_name:
            continue
        norm_name = normalize_driver(orig_name)
        driver_weighted_loads[orig_name] = 0.0
        normalized_registry_map[norm_name] = orig_name

    tracked_active_trucks = set()

    def parse_and_accumulate_trip(driver, loading_point, offloading_point, date_val, truck):
        if pd.isnull(date_val) or not driver:
            return
        date_dt = pd.to_datetime(date_val, errors='coerce')
        if pd.notnull(date_dt) and (start_cycle <= date_dt.replace(tzinfo=None) <= end_cycle):
            log_driver_norm = normalize_driver(driver)
            
            # Match logs against master records using the fuzzy registry map
            if log_driver_norm in normalized_registry_map:
                real_registry_name = normalized_registry_map[log_driver_norm]
                lp = str(loading_point).strip().upper()
                dp = str(offloading_point).strip().upper()
                
                weight = rates_map.get((lp, dp), rates_map.get(('', dp), 1.0))
                driver_weighted_loads[real_registry_name] += weight
                
            if truck:
                tracked_active_trucks.add(str(truck).strip().upper())

    # Process all operations history books
    if os.path.exists(puma_csv):
        df_p = pd.read_csv(puma_csv)
        for _, row in df_p.iterrows():
            parse_and_accumulate_trip(row.get('driver'), row.get('loading_point'), row.get('offloading_point'), row.get('date_loaded'), row.get('truck_reg'))

    if os.path.exists(secondary_csv):
        df_s = pd.read_csv(secondary_csv)
        for _, row in df_s.iterrows():
            parse_and_accumulate_trip(row.get('driver'), row.get('loading_point'), row.get('offloading_point'), row.get('date_loaded'), row.get('truck_reg'))

    if os.path.exists(trips_csv):
        df_t = pd.read_csv(trips_csv)
        for _, row in df_t.iterrows():
            parse_and_accumulate_trip(row.get('driver'), row.get('loading_point'), row.get('offloading_point'), row.get('date_loaded'), row.get('truck_reg'))

    total_drivers = len(driver_weighted_loads)
    active_trucks_count = len(tracked_active_trucks) if tracked_active_trucks else total_drivers
    
    # Check asset counts for active fleet constraints
    is_truck_scarce = (total_drivers > (active_trucks_count * 1.2))
    ratio_label = "SCARCITY PROTOCOL (Performance-Based)" if is_truck_scarce else "NORMAL PATTERN (Time-Based)"

    roster_list = []
    roster_map = df_roster.set_index('driver').to_dict('index') if not df_roster.empty else {}

    for original_driver in driver_weighted_loads.keys():
        rost_data = roster_map.get(original_driver, {})
        
        dt_truck = rost_data.get('date_truck_taken', pd.NaT)
        dt_off = rost_data.get('date_off_taken', pd.NaT)
        
        days_at_work = max(0, (today - dt_truck.replace(tzinfo=None)).days) if pd.notnull(dt_truck) else 0
        days_home_total = max(0, (today - dt_off.replace(tzinfo=None)).days) if pd.notnull(dt_off) else 0
        days_home_in_cycle = calculate_cycle_days_home(dt_off, start_cycle, end_cycle)
        
        weighted_score = driver_weighted_loads.get(original_driver, 0.0)

        roster_list.append({
            'driver': original_driver,
            'date_truck_taken': dt_truck.strftime('%Y-%m-%d') if pd.notnull(dt_truck) else "",
            'date_off_taken': dt_off.strftime('%Y-%m-%d') if pd.notnull(dt_off) else "",
            'number_of_days_at_work': days_at_work,
            'number_of_days_home_total': days_home_total,
            'number_of_days_home_cycle': days_home_in_cycle,
            'weighted_loads': round(weighted_score, 1),
            'is_at_home': days_home_total > 0
        })

    at_work_pool = [d for d in roster_list if not d['is_at_home']]
    top_3_work_drivers = [d['driver'] for d in sorted(at_work_pool, key=lambda x: x['number_of_days_at_work'], reverse=True)[:3]]

    for d in roster_list:
        if d['is_at_home']:
            limit = 4 if is_truck_scarce else 6
            if d['number_of_days_home_total'] > limit:
                d['status'] = "Due for Work"
                d['status_class'] = "flash-green"
                d['sort_order'] = 4
            else:
                d['status'] = "On Schedule"
                d['status_class'] = ""
                d['sort_order'] = 3
        else:
            if d['driver'] in top_3_work_drivers and d['number_of_days_at_work'] > 20:
                d['status'] = "Due for Home"
                d['status_class'] = "flash-red"
                d['sort_order'] = 1
            elif d['number_of_days_at_work'] > 15:
                d['status'] = "Next Batch"
                d['status_class'] = "border-blue"
                d['sort_order'] = 2
            else:
                d['status'] = "On Schedule"
                d['status_class'] = ""
                d['sort_order'] = 3

    def final_sort_ranking(item):
        group = item['sort_order']
        if group == 4:
            if is_truck_scarce:
                # Scarcity sorting variant: prioritizes lowest load weights first
                return (group, item['weighted_loads'], -item['number_of_days_home_total'])
            else:
                # Normal sorting variant: descending chronological order based on rest length
                return (group, -item['number_of_days_home_total'], item['weighted_loads'])
        else:
            return (group, -item['number_of_days_at_work'])

    meta_stats = {
        'ratio_status': ratio_label,
        'is_scarce': is_truck_scarce,
        'cycle_start': start_cycle.strftime('%Y-%m-%d'),
        'cycle_end': end_cycle.strftime('%Y-%m-%d'),
        'total_drivers': total_drivers,
        'active_trucks': active_trucks_count
    }

    return sorted(roster_list, key=final_sort_ranking), meta_stats