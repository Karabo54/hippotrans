import csv

def load_list():
    list = []

    # Open list CSV
    with open("DATA/vehicles.csv", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        # Convert each row into a dictionary
        for row in reader:
            list.append(row)

    return list
