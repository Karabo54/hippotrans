# logic/trips_duplicates.py
import csv

CSV_PATH = "DATA/trips.csv"

def order_number_exists(order_number):
    """
    Check if an order number already exists in trips.csv
    Returns True if found, False if not
    """

    # Empty order numbers are ignored (optional loads)
    if not order_number:
        return False

    with open(CSV_PATH, newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        for row in reader:
            if row.get("order_number") == order_number:
                return True

    return False
