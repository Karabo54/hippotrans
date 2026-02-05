from datetime import datetime

TRIP_STATUSES = [
    "LOADING",
    "IN TRANSIT",
    "OFFLOADED",
    "COMPLETED",
    "CANCELLED"
]
def parse_date(date_str):
    """
    Converts YYYY-MM-DD string to datetime.date
    Returns None if empty or invalid
    """
    if not date_str:
        return None

    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None
def validate_trip(trip):
    """
    trip: dict containing trip fields
    Returns a list of validation error messages
    """

    errors = []

    # Required fields
    required_fields = [
        "date_loaded",
        "loading_point",
        "truck_reg",
        "driver",
        "status"
    ]

    for field in required_fields:
        if not trip.get(field):
            errors.append(f"{field.replace('_', ' ').title()} is required")

    # Status validation
    status = trip.get("status")
    if status not in TRIP_STATUSES:
        errors.append("Invalid trip status")

    # Date validation
    date_loaded = parse_date(trip.get("date_loaded"))
    date_offloaded = parse_date(trip.get("date_offloaded"))

    if trip.get("date_loaded") and not date_loaded:
        errors.append("Invalid date loaded format")

    if trip.get("date_offloaded") and not date_offloaded:
        errors.append("Invalid date offloaded format")

    # Logical date rule
    if date_loaded and date_offloaded:
        if date_offloaded < date_loaded:
            errors.append("Date offloaded cannot be before date loaded")

    # Status-based rules
    if status == "OFFLOADED":
        if not trip.get("dn_number"):
            errors.append("DN number is required when trip is offloaded")

        if not date_offloaded:
            errors.append("Date offloaded is required when trip is offloaded")

    if status == "COMPLETED":
        if not trip.get("dn_number") or not date_offloaded:
            errors.append("Completed trips must be offloaded first")

    return errors

ALLOWED_TRANSITIONS = {
    None: ["LOADING"],
    "LOADING": ["IN TRANSIT", "CANCELLED"],
    "IN TRANSIT": ["OFFLOADED", "CANCELLED"],
    "OFFLOADED": ["COMPLETED"],
    "COMPLETED": [],
    "CANCELLED": []
}
def validate_status_transition(old_status, new_status):
    """
    Ensures trip status moves correctly
    """
    allowed = ALLOWED_TRANSITIONS.get(old_status, [])

    if new_status not in allowed:
        return False

    return True
