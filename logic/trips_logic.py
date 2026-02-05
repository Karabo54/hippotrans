# logic/trips_logic.py
import csv
from logic.trips_validation import validate_trip
from logic.trips_utils import parse_date, get_month_name
from logic.trips_duplicates import order_number_exists

CSV_PATH = "DATA/trips.csv"

def process_new_trip(form_data):
    # 1️⃣ Validate required fields
    errors = validate_trip(form_data)
    if errors:
        return False, errors

    # 2️⃣ Duplicate order number check
    order_number = form_data.get("order_number")

    if order_number_exists(order_number):
        return False, [f"Order number {order_number} already exists"]

    # 3️⃣ Parse date & derive month
    date_loaded = parse_date(form_data["date_loaded"])
    month = get_month_name(date_loaded)

    # 4️⃣ Prepare CSV row (MATCH HEADER ORDER)
    row = [
        form_data.get("date_loaded"),
        form_data.get("loading_point"),
        form_data.get("truck_reg"),
        form_data.get("trailer_reg"),
        form_data.get("driver"),
        form_data.get("customer"),
        order_number,
        form_data.get("product"),
        form_data.get("status"),
        form_data.get("position"),
        form_data.get("offloading_point"),  # ✅ corrected
        form_data.get("date_offloaded"),
        form_data.get("dn_number"),
        form_data.get("eta"),
        month
    ]

    # 5️⃣ Write to CSV
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(row)

    return True, None
