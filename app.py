from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
import csv
import os
import smtplib
from email.message import EmailMessage
from collections import defaultdict
from datetime import datetime, date, timedelta
from utils.load_fuel import load_fuel, add_fuel_entry, fuel_consumption_stats
from utils.load_trips import load_trips


# -------------------- IMPORTS FROM YOUR PROJECT --------------------
from utils.load_drivers import load_drivers
from utils.load_trips import load_trips, add_trip, delete_trip, update_trip, update_status
from utils.dashboard_stats import dashboard_stats
from utils.load_list import load_list
from utils.group_trips import group_trips_by_month
from logic.vehicles import load_vehicles, save_vehicles, update_vehicle_km_from_trip
from utils.load_breakdowns import load_breakdowns, add_breakdown, update_breakdown_status
from utils.load_services import load_services, add_service_entry
from utils.load_compliance import load_compliance, enrich_compliance_records, get_current_month_expiries
from utils.load_dashboard import load_dashboard_stats
from datetime import datetime
from utils.load_fatigue import (
    save_working_hours,
    get_roster_status, summarize_by_driver_week
)
from flask import flash, redirect, url_for
from utils.load_fatigue import (
    load_working_hours,
    add_working_hour,
    delete_working_hour,
    update_working_hour,
    enrich_records,
    group_by_year_month_driver,
    summarize_by_driver_month,
    summarize_by_driver_week,
    get_roster_status
)

# -------------------------------------------------------------------

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-later"

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

SERVICE_INTERVAL_KM = 40000  # Service interval


# -------------------- HELPER FUNCTIONS --------------------

def normalize_customer(name):
    if not name:
        return "ADHOC"
    name = name.strip().upper()
    if name in ["ENGEN", "OVK", "DUCAT", "GREENFORCE", "ADHOC"]:
        return name
    return name  # keep other valid customers


def calculate_monthly_trip_stats(trips):
    """
    Calculates operational summary stats per month.
    Designed for logistics performance dashboards.
    """

    stats = {
        "turnaround_by_point": {},
        "fuel_by_point": {},
        "km_by_point": {},
        "customer_activity": {
            "ENGEN": 0,
            "OVK": 0,
            "Ducat": 0,
            "GreenForce": 0,
            "Adhoc": 0
        },
        "active_drivers": set(),
        "active_trucks": set(),
        "idle_trucks": set(),
        "route_turnaround_averages": {},
        "fastest_route": None,
        "slowest_route": None,
    }

    turnaround_accumulator = {}
    km_accumulator = {}
    fuel_loaded_acc = {}
    fuel_offloaded_acc = {}

    for trip in trips:
        status = trip.get("status", "").upper()
        off_point = trip.get("offloading_point", "UNKNOWN")
        customer = normalize_customer(trip.get("customer"))
        driver = trip.get("driver")
        truck = trip.get("truck_reg")

        # Only completed trips count for performance metrics
        if status == "OFFLOADED":
            # ---------------- TURNAROUND ----------------
            time_taken = trip.get("time_taken")  # Format: "74 h 02 m"
            if time_taken:
                try:
                    parts = time_taken.replace("h", "").replace("m", "").split()
                    hours = int(parts[0])
                    minutes = int(parts[1])
                    total_hours = hours + (minutes / 60)

                    turnaround_accumulator.setdefault(off_point, []).append(total_hours)
                except:
                    pass

            # ---------------- KM ----------------
            km = safe_int(trip.get("km_travelled"))
            km_accumulator[off_point] = km_accumulator.get(off_point, 0) + km

            # ---------------- FUEL ----------------
            loaded = safe_int(trip.get("litres_loaded"))
            offloaded = safe_int(trip.get("litres_offloaded"))

            fuel_loaded_acc[off_point] = fuel_loaded_acc.get(off_point, 0) + loaded
            fuel_offloaded_acc[off_point] = fuel_offloaded_acc.get(off_point, 0) + offloaded

        # ---------------- CUSTOMER ACTIVITY ----------------
        if customer in stats["customer_activity"]:
            stats["customer_activity"][customer] += 1
        else:
            stats["customer_activity"]["Adhoc"] += 1

        # ---------------- ACTIVE DRIVERS & TRUCKS ----------------
        if status in ["LOADING", "IN TRANSIT", "OFFLOADED"]:
            if driver:
                stats["active_drivers"].add(driver)
            if truck:
                stats["active_trucks"].add(truck)

    # ---------------- TURNAROUND AVERAGES PER ROUTE ----------------
    for point, hours_list in turnaround_accumulator.items():
        avg = round(sum(hours_list) / len(hours_list), 1)
        stats["turnaround_by_point"][point] = avg
        stats["route_turnaround_averages"][point] = avg

    # ---------------- FUEL BY ROUTE ----------------
    for point in fuel_loaded_acc:
        stats["fuel_by_point"][point] = {
            "loaded": fuel_loaded_acc.get(point, 0),
            "offloaded": fuel_offloaded_acc.get(point, 0),
            "difference": fuel_loaded_acc.get(point, 0) - fuel_offloaded_acc.get(point, 0),
        }

    # ---------------- KM BY ROUTE ----------------
    stats["km_by_point"] = km_accumulator

    # ---------------- FASTEST & SLOWEST ROUTES ----------------
    if stats["route_turnaround_averages"]:
        stats["fastest_route"] = min(stats["route_turnaround_averages"], key=stats["route_turnaround_averages"].get)
        stats["slowest_route"] = max(stats["route_turnaround_averages"], key=stats["route_turnaround_averages"].get)

    # ---------------- IDLE TRUCKS ----------------
    all_trucks = {trip.get("truck_reg") for trip in trips if trip.get("truck_reg")}
    stats["idle_trucks"] = all_trucks - stats["active_trucks"]

    # Final counts
    stats["active_driver_count"] = len(stats["active_drivers"])
    stats["active_truck_count"] = len(stats["active_trucks"])
    stats["idle_truck_count"] = len(stats["idle_trucks"])

    return stats


def safe_int(value, default=0):
    """Safely convert a value to int."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def calculate_service_status(vehicle):
    """
    Calculate service status based on current_km and last_service_km.
    Returns (status, km_to_service)
    """
    current_km = safe_int(vehicle.get("current_km"))
    last_service_km = safe_int(vehicle.get("last_service_km"))

    km_since_service = current_km - last_service_km
    km_to_service = SERVICE_INTERVAL_KM - km_since_service

    if km_to_service <= 0:
        return "OVERDUE", km_to_service
    elif km_to_service <= 1000:
        return "DUE", km_to_service
    else:
        return "OK", km_to_service


def km_update_required(vehicle):
    """Return True if KM was not updated this week (Monday–Sunday)."""
    last_update = vehicle.get("last_km_update")
    if not last_update:
        return True

    last_update_date = datetime.strptime(last_update, "%Y-%m-%d").date()
    today = datetime.today().date()
    monday = today - timedelta(days=today.weekday())

    return last_update_date < monday

def auto_update_vehicle_km_from_trips():
    """Auto-update vehicle current_km from trips without overwriting higher manual values."""
    vehicles = load_vehicles()
    trips = load_trips()
    today_str = datetime.today().strftime("%Y-%m-%d")

    # Build a lookup for vehicles by truck_reg
    vehicle_map = {v.get("truck_reg"): v for v in vehicles}

    for trip in trips:
        truck_reg = trip.get("truck_reg")
        if not truck_reg:
            continue

        vehicle = vehicle_map.get(truck_reg)
        if not vehicle:
            continue

        current_km = safe_int(vehicle.get("current_km"))

        status = (trip.get("status") or "").upper()
        offloading_km = safe_int(trip.get("offloading_km"))
        loading_km = safe_int(trip.get("loading_km"))

        candidate_km = current_km

        # Prefer offloading km if trip is completed
        if status == "OFFLOADED" and offloading_km > 0:
            candidate_km = offloading_km

        # Otherwise consider loading km
        elif loading_km > 0:
            candidate_km = loading_km

        # Only update if new KM is higher than stored KM
        if candidate_km > current_km:
            vehicle["current_km"] = str(candidate_km)
            vehicle["last_km_update"] = today_str

            # Initialize last_service_km if empty
            if not vehicle.get("last_service_km"):
                vehicle["last_service_km"] = vehicle["current_km"]

    save_vehicles(vehicles)


# -------------------- VEHICLE ROUTES --------------------


@app.route("/dashboard")
def dashboard():
    vehicles = load_vehicles()
    trips = load_trips()
    fuel = load_fuel()
    compliance = load_compliance()   # ✅ no argument
    breakdowns = load_breakdowns()

    enriched_compliance = enrich_compliance_records(compliance)

    expired_docs = [d for d in enriched_compliance if d["status"] == "Expired"]
    almost_due_docs = [d for d in enriched_compliance if d["status"] == "Almost Due"]
    open_breakdowns = [b for b in breakdowns if b.get("status", "").lower() != "resolved"]

    # Trips per month
    from collections import defaultdict
    trips_by_month = defaultdict(int)
    for t in trips:
        if t.get("loading_date"):
            month = t["loading_date"][:7]  # YYYY-MM
            trips_by_month[month] += 1

    # Fuel per truck
    fuel_by_truck = defaultdict(float)
    for f in fuel:
        litres_str = f.get("litres", "").strip()
        litres = float(litres_str) if litres_str else 0.0
        fuel_by_truck[f["truck_reg"]] += litres

    stats = {
        "total_vehicles": len(vehicles),
        "active_vehicles": len([v for v in vehicles if v.get("status", "").lower() == "active"]),
        "total_trips": len(trips),
        "open_breakdowns": len(open_breakdowns),
        "expired_docs_count": len(expired_docs),
        "almost_due_docs_count": len(almost_due_docs),
        "total_fuel": round(sum(fuel_by_truck.values()), 2),
        "fuel_cost": 0,  # placeholder for now
    }

    return render_template(
        "dashboard.html",
        stats=stats,
        expired_docs=expired_docs,
        almost_due_docs=almost_due_docs,
        trips_by_month=dict(trips_by_month),
        fuel_by_truck=dict(fuel_by_truck),
    )


@app.route("/fatigue/hours", methods=["GET", "POST"])
def fatigue_hours():
    if request.method == "POST":
        try:
            entry = {
                "date": request.form.get("date"),
                "driver_name": request.form.get("driver_name"),
                "start_time": request.form.get("start_time"),
                "end_time": request.form.get("end_time"),
                "off_day": request.form.get("off_day", "no"),
                "after_hours_reason": request.form.get("after_hours_reason", "")
            }
            add_working_hour(entry)
            flash("✅ Working hours logged successfully!", "success")
            return redirect("/fatigue/hours")
        except Exception as e:
            flash(f"❌ Error saving record: {str(e)}", "error")
     # Add index for edit/delete
    records = load_working_hours()
    for i, r in enumerate(records):
        r["index"] = i
    
    enriched = enrich_records(records)

    structure = group_by_year_month_driver(enriched)
    monthly_summary = summarize_by_driver_month(enriched)
    weekly_summary = summarize_by_driver_week(enriched)
    rotation = get_roster_status()

    # Defaults for current date
    today = date.today()
    default_year = today.year
    default_month = today.strftime("%B")
    records = load_working_hours()

   

    

    return render_template(
        "fatigue/hours.html",
        structure=structure,
        monthly_summary=monthly_summary,
        weekly_summary=weekly_summary,
        rotation=rotation,
        default_year=default_year,
        default_month=default_month
    )


@app.route("/fatigue/hours/delete/<int:index>", methods=["POST"])
def delete_fatigue_entry(index):
    delete_working_hour(index)
    flash("✅ Entry deleted successfully.", "success")
    return redirect(url_for("fatigue_hours"))


@app.route("/fatigue/update", methods=["POST"])
def update_fatigue():
    records = load_working_hours()
    record_id = request.form.get("id")

    for r in records:
        
            r["date"] = request.form.get("date")
            r["driver_name"] = request.form.get("driver_name")
            r["start_time"] = request.form.get("start_time")
            r["end_time"] = request.form.get("end_time")
            r["off_day"] = request.form.get("off_day")
            r["after_hours_reason"] = request.form.get("after_hours_reason")
            break

    save_working_hours(records)
    flash("Working hours updated successfully ✅", "success")
    return redirect("/fatigue/hours")


@app.route("/vehicles/compliance")
def vehicle_compliance():
    print("🚨 Compliance route HIT")

    records = load_compliance()
    print("🚨 Records from CSV:", records)

    enriched = enrich_compliance_records(records)

    trucks = {}
    for r in enriched:
        trucks.setdefault(r["truck_reg"], []).append(r)

    print("🚨 Grouped trucks:", trucks)

    return render_template("vehicles/compliance.html", trucks=trucks)

@app.route("/vehicles/compliance/expiries")
def compliance_expiries():
    records = load_compliance()
    expiring = get_current_month_expiries(records)
    return render_template("vehicles/compliance_expiries.html", records=expiring)


@app.route("/vehicles/services/<truck_reg>", methods=["GET", "POST"])
def vehicle_service_history(truck_reg):
    if request.method == "POST":
        add_service_entry(request.form)
        flash("✅ Service record added successfully!", "success")
        return redirect(url_for("vehicle_service_history", truck_reg=truck_reg))

    all_services = load_services()
    truck_services = [s for s in all_services if s.get("truck_reg") == truck_reg]

    return render_template(
        "vehicles/service_history.html",
        truck_reg=truck_reg,
        services=truck_services
    )

@app.route("/fuel", methods=["GET", "POST"])
def fuel():
    if request.method == "POST":
        add_fuel_entry(request.form)
        flash("⛽ Fuel entry added successfully!", "success")
        return redirect(url_for("fuel"))

    fuel_logs = load_fuel()
    trips = load_trips()

    month = request.args.get("month")  # YYYY-MM
    stats = fuel_consumption_stats(fuel_logs, trips, month)

    return render_template("fuel/fuel.html", fuel_logs=fuel_logs, fuel_stats=stats, selected_month=month)

@app.route("/vehicles")
def vehicle_list():
    vehicles = load_vehicles()
    trips = load_trips()

    # Build active truck set from trips
    active_trucks = {t["truck_reg"] for t in trips if t.get("status") not in ["OFFLOADED", "COMPLETED"]}

    enriched = []
    service_due = 0
    service_overdue = 0
    km_missing = 0
    assigned = 0
    unassigned = 0

    for v in vehicles:
        status, km_to_service = calculate_service_status(v)
        km_warning = km_update_required(v)

        if status == "OVERDUE":
            service_overdue += 1
        elif status == "DUE":
            service_due += 1

        if km_warning:
            km_missing += 1

        if v.get("driver"):
            assigned += 1
        else:
            unassigned += 1

        enriched.append({
            **v,
            "service_status": status,
            "km_to_service": km_to_service,
            "km_due_warning": km_warning,
            "truck_status": "ACTIVE" if v.get("truck_reg") in active_trucks else "IDLE"
        })

    summary = {
        "total": len(vehicles),
        "service_overdue": service_overdue,
        "service_due": service_due,
        "km_missing": km_missing,
        "assigned": assigned,
        "unassigned": unassigned,
        "active_trucks": len(active_trucks),
        "idle_trucks": len(vehicles) - len(active_trucks)
    }

    return render_template("vehicles.html", vehicles=enriched, summary=summary)


@app.route("/vehicles/update_km/<truck_reg>", methods=["POST"])
def update_km(truck_reg):
    new_km = safe_int(request.form.get("new_km"))
    vehicles = load_vehicles()
    updated = False

    for v in vehicles:
        if v.get("truck_reg") == truck_reg:
            current_km = safe_int(v.get("current_km"))
            if new_km < current_km:
                flash("❌ New KM cannot be less than current KM.", "error")
                return redirect("/vehicles")

            v["current_km"] = str(new_km)
            v["last_km_update"] = datetime.today().strftime("%Y-%m-%d")

            # If last_service_km is empty, initialize it
            if not v.get("last_service_km"):
                v["last_service_km"] = v["current_km"]

            updated = True
            break

    if updated:
        save_vehicles(vehicles)
        flash(f"✅ KM updated for {truck_reg}", "success")
    else:
        flash("❌ Vehicle not found.", "error")

    return redirect("/vehicles")


@app.route("/breakdowns", methods=["GET", "POST"])
def breakdowns():
    if request.method == "POST":
        add_breakdown(request.form)
        flash("✅ Breakdown reported successfully!", "success")
        return redirect(url_for("breakdowns"))

    breakdowns = load_breakdowns()
    vehicles = load_vehicles()
    drivers = load_drivers()

    return render_template("breakdowns/breakdowns.html",
                           breakdowns=breakdowns,
                           vehicles=vehicles,
                           drivers=drivers)

@app.route("/breakdowns/update/<breakdown_id>", methods=["POST"])
def update_breakdown(breakdown_id):
    status = request.form.get("status")
    repair_cost = request.form.get("repair_cost")
    workshop = request.form.get("workshop")
    notes = request.form.get("notes")

    update_breakdown_status(breakdown_id, status, repair_cost, workshop, notes)
    flash("✅ Breakdown updated!", "success")
    return redirect(url_for("breakdowns"))


# -------------------- TRIPS ROUTES --------------------

@app.route("/trips", methods=["GET", "POST"])
def trips():
    if request.method == "POST":
        success = add_trip(request.form)
        if not success:
            flash("❌ Order number already exists! Please use a different order.", "error")
        else:
            flash("✅ Trip added successfully!", "success")
        return redirect(url_for("trips"))
    auto_update_vehicle_km_from_trips()
    trips = load_trips()
    trips_by_month = group_trips_by_month(trips)
    current_month = datetime.now().strftime("%B")

    # Calculate stats per month
    monthly_stats = {}
    for month, month_trips in trips_by_month.items():
        monthly_stats[month] = calculate_monthly_trip_stats(month_trips)


    return render_template(
    "trips/trips.html",
    trips_by_month=trips_by_month,
    monthly_stats=monthly_stats,
    current_month=current_month
)



@app.route("/trips/upload", methods=["GET", "POST"])
def upload_trips():
    if request.method == "POST":
        file = request.files["file"]
        file.save("DATA/trips.csv")
        return redirect(url_for("trips"))
    return render_template("trips/upload.html")


@app.route("/trips/delete/<order_number>", methods=["POST"])
def delete_trip_route(order_number):
    delete_trip(order_number)
    flash("Trip deleted successfully.", "success")
    return redirect(url_for("trips"))


@app.route("/trips/update/<order_number>", methods=["POST"])
def update_trip_route(order_number):
    update_trip(order_number, request.form)
    flash("Trip updated successfully.", "success")
    return redirect(url_for("trips"))


@app.route("/trips/status/<order_number>", methods=["POST"])
def update_status_route(order_number):
    status = request.form.get("status")
    position = request.form.get("position")
    update_status(order_number, status, position)

    # 🔄 Auto-update vehicle KM when OFFLOADED
    if status == "OFFLOADED":
        trips = load_trips()
        for t in trips:
            if t["order_number"] == order_number:
                offloading_km = safe_int(t.get("offloading_km"))
                truck_reg = t.get("truck_reg")
                if offloading_km and truck_reg:
                    update_vehicle_km_from_trip(truck_reg, offloading_km)
                break

    flash("Trip status updated.", "success")
    return redirect(url_for("trips"))


@app.route("/trips/edit/<order_number>", methods=["POST"])
def edit_trip_route(order_number):
    update_trip(order_number, request.form)
    flash("Trip updated successfully.", "success")
    return redirect(url_for("trips"))


# -------------------- COMPLIANCE & DASHBOARD --------------------



@app.route("/vehicles/compliance")
def compliance():
    trucks = load_compliance("truck_compliance.csv")
    trailers = load_compliance("trailer_compliance.csv")
    today = date.today()

    return render_template(
        "vehicles/compliance.html",
        trucks=trucks,
        trailers=trailers,
        today=today
    )


@app.route("/vehicles/list")
def vehicles_list():
    list_data = load_list()
    return render_template("vehicles/list.html", list=list_data)



# -------------------- DRIVERS --------------------

@app.route("/drivers/drivers")
def drivers():
    drivers = load_drivers()
    return render_template("drivers/drivers.html", drivers=drivers)


@app.route("/drivers/contacts")
def driver_contacts():
    return render_template("drivers/contacts.html")


@app.route("/drivers/violations")
def driver_violations():
    return render_template("drivers/violations.html")


@app.route("/drivers/training")
def driver_training():
    return render_template("drivers/training.html")


@app.route("/drivers/loads")
def driver_loads():
    return render_template("drivers/loads.html")


@app.route("/drivers/allowance")
def driver_allowance():
    return render_template("drivers/allowance.html")


# -------------------- DOCUMENTS --------------------

@app.route("/documents")
def documents():
    files = os.listdir(UPLOAD_FOLDER)
    return render_template("documents.html", files=files)


@app.route("/documents/upload", methods=["POST"])
def upload_doc():
    file = request.files.get("pdf_file")
    if file and file.filename.endswith(".pdf"):
        file.save(os.path.join(UPLOAD_FOLDER, file.filename))
    return redirect(url_for("documents"))


@app.route("/drivers/docs/download/<filename>")
def download_doc(filename):
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)


@app.route("/drivers/docs/view/<filename>")
def view_doc(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route("/drivers/docs/send_email", methods=["POST"])
def send_doc_email():
    to_email = request.form["to_email"]
    filename = request.form["filename"]
    filepath = os.path.join(UPLOAD_FOLDER, filename)

    msg = EmailMessage()
    msg['Subject'] = f'Document: {filename}'
    msg['From'] = 'your_email@example.com'  # Replace with your email
    msg['To'] = to_email

    with open(filepath, 'rb') as f:
        msg.add_attachment(f.read(), maintype='application', subtype='pdf', filename=filename)

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login('your_email@example.com', 'your_app_password')
        smtp.send_message(msg)

    return redirect(url_for("documents"))


# -------------------- RUN APP --------------------

if __name__ == "__main__":
    app.run(debug=True)
