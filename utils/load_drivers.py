import csv

def load_drivers():
    drivers = []

    # Open drivers CSV
    with open("DATA/drivers.csv", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        # Convert each row into a dictionary
        for row in reader:
            drivers.append(row)

    return drivers
