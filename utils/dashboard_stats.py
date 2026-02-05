import csv

def dashboard_stats():
    total_trips = 0
    pending = 0
    delivered = 0

    with open("DATA/trips.csv", newline="", encoding="latin-1") as f:
        reader = csv.DictReader(f)

        for row in reader:
            total_trips += 1

            status = row.get("STATUS", "").upper()

            if status == "PENDING":
                pending += 1
            elif status == "OFFLOADED":
                delivered += 1

    return {
        "total_trips": total_trips,
        "pending": pending,
        "delivered": delivered
    }
