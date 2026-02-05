from datetime import datetime
from collections import defaultdict

def group_trips_by_month(trips):
    grouped = defaultdict(list)

    for trip in trips:
        date_str = trip.get("date_loaded")

        if not date_str:
            continue  # skip empty dates

        try:
            # Accept both formats: 2026-01-12 or 2026/01/12
            if "-" in date_str:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            else:
                date_obj = datetime.strptime(date_str, "%Y/%m/%d")

            month_name = date_obj.strftime("%B")
            grouped[month_name].append(trip)

        except Exception as e:
            print("❌ Date parsing failed:", date_str, e)

    return dict(grouped)
