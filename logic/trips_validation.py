# logic/trips_validation.py

REQUIRED_FIELDS = [
    "date_loaded",
    "loading_point",
    "truck_reg",
    "trailer_reg",
    "driver",
    "status"
]

def validate_trip(form_data):
    errors = []

    for field in REQUIRED_FIELDS:
        if not form_data.get(field):
            errors.append(f"{field.replace('_', ' ').title()} is required")

    return errors
