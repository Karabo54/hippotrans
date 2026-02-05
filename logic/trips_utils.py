# logic/trips_utils.py
from datetime import datetime

def parse_date(date_str):
    """
    Accepts YYYY-MM-DD (HTML date input)
    Returns datetime.date
    """
    return datetime.strptime(date_str, "%Y-%m-%d").date()

def get_month_name(date_obj):
    return date_obj.strftime("%B")
