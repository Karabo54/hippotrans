import os,json,io
import csv,time
import uuid
import pdfkit
from flask import make_response
from logic.vehicles import auto_update_all_vehicle_km
import tempfile
import smtplib
import pandas as pd
from fpdf import FPDF
from io import BytesIO
from collections import defaultdict
from datetime import datetime, date, timedelta
from functools import wraps
from flask import abort
# Flask Core & Extensions
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, send_file,jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy import MetaData
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from utils.puma_helpers import get_puma_summary, get_puma_active_trips
# Email handling
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from flask import make_response
# PDF Generation
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# -------------------- PROJECT UTILS --------------------
from utils.load_drivers import load_drivers
from utils.load_list import load_list
from utils.group_trips import group_trips_by_month
from utils.dashboard_stats import dashboard_stats
from utils.load_dashboard import load_dashboard_stats
from utils.load_incidents import load_incidents
from utils.invoice_generator import create_pdf
from flask import render_template, request, redirect, url_for, flash
from utils.workshop import load_workshop_data, save_job_card, convert_breakdown_to_jobcard,close_workshop_job,save_all_workshop_data
# Trip Management
from utils.load_trips import (
    load_trips, add_trip,
    update_trip, update_status,perform_trip_deletion
)

# Vehicle & Maintenance
from logic.vehicles import load_vehicles, save_vehicles, update_vehicle_km_from_trip
from utils.load_breakdowns import load_breakdowns, add_breakdown, update_breakdown_status
from utils.load_services import load_services, add_service_entry
from utils.load_compliance import get_compliance_data

# Fatigue & Roster Logic
from utils.load_fatigue import (
    load_working_hours, add_working_hour, delete_working_hour, 
    update_working_hour, save_working_hours, load_fatigue,
    enrich_records, group_by_year_month_driver, 
    summarize_by_driver_month, summarize_by_driver_week, 
    get_roster_status,calculate_global_customer_totals,calculate_monthly_customer_totals
)
from utils.roster import process_advanced_roster_data
from utils.drivers_module import get_bto_registry, delete_bto_entry, get_bto_stats

# Finance & Fuel
from utils.finance_module import get_finance_data
from utils.fuel_logic import (
    load_fuel, save_fuel, add_fuel_entry, 
    fuel_consumption_stats, analyze_fuel_health
)

# -------------------- CONFIGURATION --------------------

app = Flask(__name__)
app.secret_key = 'some_very_secret_key_here_12345'

# Database Configuration (Place for SQLAlchemy setup)
# db = SQLAlchemy(app)
# migrate = Migrate(app, db)

# Add this near the top of app.py
PUMA_TRIPS_CSV = 'data/puma_trips.csv'
CSV_PATH = os.path.join('DATA', 'roster.csv')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'DATA')
#=====================DATABASE=======================================
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy import MetaData

# 1. Database Configuration
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'fleet.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 2. SQLite Naming Convention (The fix for your previous error)
convention = {
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}
metadata = MetaData(naming_convention=convention)

# 3. Initialize ONCE
db = SQLAlchemy(app, metadata=metadata)
migrate = Migrate(app, db, render_as_batch=True)
class Driver(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    # This links the driver to their loads automatically
    loads = db.relationship('Trip', backref='driver_ref', lazy=True)

class Vehicle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    truck_reg = db.Column(db.String(20), unique=True, nullable=False)
    truck_type = db.Column(db.String(50))
    truck_vin = db.Column(db.String(50))
    trailer_reg = db.Column(db.String(20))
    trailer_type = db.Column(db.String(50))
    trailer_vin = db.Column(db.String(50))
    pto_avail = db.Column(db.String(10))
    driver = db.Column(db.String(100))
    current_km = db.Column(db.Float, default=0.0)
    last_km_update = db.Column(db.DateTime)
    last_service_km = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(50))
    lat = db.Column(db.Float)
    lng = db.Column(db.Float)

    # This looks for 'vehicle_id' in the Trip table
    trips = db.relationship('Trip', backref='vehicle_ref', lazy=True)

class Trip(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(50), unique=True)
    driver_id = db.Column(db.Integer, db.ForeignKey('driver.id'))
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicle.id'))
    
    # Dates & Times
    date_loaded = db.Column(db.DateTime)
    date_offloaded = db.Column(db.DateTime) # This was likely missing!
    loading_time = db.Column(db.String(50))
    offloading_time = db.Column(db.String(50))
    time_taken = db.Column(db.String(50))
    eta = db.Column(db.String(50))

    # Logistics
    loading_point = db.Column(db.String(100))
    offloading_point = db.Column(db.String(100))
    truck_reg = db.Column(db.String(20))
    trailer_reg = db.Column(db.String(20))
    customer = db.Column(db.String(100))
    product = db.Column(db.String(100))
    status = db.Column(db.String(50))
    position = db.Column(db.String(50))
    dn_number = db.Column(db.String(50))
    allowance_status = db.Column(db.String(50))

    # Numbers
    litres_loaded = db.Column(db.Float, default=0.0)
    litres_offloaded = db.Column(db.Float, default=0.0)
    difference = db.Column(db.Float, default=0.0)
    loading_km = db.Column(db.Float, default=0.0)
    offloading_km = db.Column(db.Float, default=0.0)
    km_travelled = db.Column(db.Float, default=0.0)
#====================================================================

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

SERVICE_INTERVAL_KM = 40000  # Service interval
#-----------------------LOGIN--------------------------------------------

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- USER MODEL ---
class User(UserMixin):
    def __init__(self, username, password, role):
        self.id = username # Flask-Login needs an 'id'
        self.username = username
        self.password = password
        self.role = role

# Helper: Find user in CSV
def find_user(username):
    try:
        with open('users.csv', mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # .strip() removes any accidental spaces from the CSV or the input
                if row['username'].strip() == username.strip():
                    return User(
                        row['username'].strip(), 
                        row['password'].strip(), # Critical to strip the hash too
                        row['role'].strip()
                    )
    except FileNotFoundError:
        print("DEBUG: users.csv file is missing!")
    return None

@login_manager.user_loader
def load_user(username):
    
    return find_user(username)

def generate_pdf_response(html_content):
    # Create a buffer to store the PDF
    result = io.BytesIO()

    # Convert HTML to PDF
    pisa_status = pisa.CreatePDF(html_content, dest=result)

    if pisa_status.err:
        return "Error generating PDF", 500

    # Create the response
    response = make_response(result.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'inline; filename=loading_advice.pdf'
    return response

def role_required(allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if current_user.role not in allowed_roles:
                abort(403) # "Forbidden" page
            return f(*args, **kwargs)
        return decorated_function
    return decorator


@app.route('/')
def index_login():
    # If the user is already logged in, take them to the dashboard
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    # Otherwise, show the login page
    return redirect(url_for('login'))

# --- ROUTES ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = find_user(username) # This looks in your CSV
        
        if user:
            # This checks the typed password against the hashed CSV password
            if check_password_hash(user.password, password):
                login_user(user)
                print(f"DEBUG: Login Successful for {username}")
                return redirect(url_for('dashboard'))
            else:
                print(f"DEBUG: Password incorrect for {username}")
                flash('Invalid password.', 'danger')
        else:
            print(f"DEBUG: User {username} not found in CSV")
            flash('Username does not exist.', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


#-------------------------------------------------------------------

# -------------------- HELPER FUNCTIONS --------------------
def safe_parse_date(date_str):
    if not date_str: return datetime.today().date()
    return datetime.strptime(date_str.replace("/", "-"), "%Y-%m-%d").date()



def save_breakdowns(breakdown_list):
    file_path = "DATA/breakdowns.csv"
    # Ensure these headers match your CSV 100%
    fieldnames = [
        "breakdown_id", "truck_reg", "driver", "location", 
        "issue_description", "reported_date", "reported_time", 
        "km_at_breakdown", "status", "repair_cost", "workshop", 
        "downtime_hours", "notes"
    ]
    
    try:
        with open(file_path, mode="w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            if breakdown_list:  # Only write if there is data
                writer.writerows(breakdown_list)
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False
    
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
    current_km = safe_int(vehicle.get("current_km"))
    next_goal = safe_int(vehicle.get("next_service_km"))

    # If next_service_km is empty or 0, fallback to current + 40,000
    if next_goal == 0:
        next_goal = current_km + 40000

    km_to_service = next_goal - current_km

    if km_to_service <= 0:
        return "OVERDUE", km_to_service
    elif km_to_service <= 2000:
        return "DUE", km_to_service
    else:
        return "OK", km_to_service

def km_update_required(vehicle):
    """Return True if KM was not updated this week (Monday–Sunday)."""
    last_update = vehicle.get("last_km_update")
    
    if not last_update:
        return True

    # Then use it like:
    last_update_date = safe_parse_date(last_update)
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

import platform
import subprocess


def get_pdfkit_config():
    if platform.system() == "Windows":
        # Your local Windows path
        return pdfkit.configuration(wkhtmltopdf=r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe')
    else:
        # On Linux/Render, the buildpack makes it available in the PATH
        # We find the path automatically
        try:
            # 'which' command finds the location of the executable
            path = subprocess.check_output(['which', 'wkhtmltopdf']).decode().strip()
            return pdfkit.configuration(wkhtmltopdf=path)
        except Exception:
            # Fallback for Render environments
            return pdfkit.configuration(wkhtmltopdf='/usr/bin/wkhtmltopdf')

# Integration Example:
# Replace your current pdfkit.from_string(...) calls with:
# pdf = pdfkit.from_string(html_content, False, configuration=get_pdfkit_config())

def load_food_allowance():
    allowances = []
    file_path = "DATA/food_allowances.csv"
    
    # Check if file exists to prevent FileNotFoundError
    if not os.path.exists(file_path):
        print(f"⚠️ {file_path} not found. Returning empty list.")
        return []

    try:
        with open(file_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Ensure 'amount' is treated as a number for future math
                try:
                    row['amount'] = float(row.get('amount', 0) or 0)
                except ValueError:
                    row['amount'] = 0.0
                
                allowances.append(row)
    except Exception as e:
        print(f"❌ Error loading food allowances: {e}")
        return []
        
    return allowances

# -------------------- VEHICLE ROUTES --------------------

#===========================CALENDER===============================

import os
import pandas as pd
from flask import session, flash, request, redirect
from datetime import datetime, timedelta


@app.before_request
def check_reminders():
    # 1. Ignore static files and images
    if request.endpoint in ['static', 'favicon'] or not request.endpoint:
        return

    # 2. Initialize the dismiss list in session
    if 'dismissed_reminders' not in session:
        session['dismissed_reminders'] = []

    # 3. Path MUST match your saving route
    FILE_PATH = os.path.join("DATA", "calendar.csv")
    
    if os.path.exists(FILE_PATH):
        try:
            # Read CSV and drop any completely empty rows
            df = pd.read_csv(FILE_PATH).dropna(subset=['event_date', 'title'])
            
            today = datetime.now().date()
            five_days_out = today + timedelta(days=5)

            for index, event in df.iterrows():
                # We use the row 'index' to make the ID truly unique
                event_id = f"id_{index}_{event['event_date']}"
                
                # If user clicked 'X' for this specific row, don't flash it
                if event_id in session['dismissed_reminders']:
                    continue

                # Parse the date
                try:
                    ev_date = datetime.strptime(str(event['event_date']), '%Y-%m-%d').date()
                except:
                    continue # Skip rows with bad dates
                
                # Check if date is in the 5-day window
                if today <= ev_date <= five_days_out:
                    # Priority: SERVICE = Red (danger), BOOKING = Blue (info)
                    category = "info"
                    if str(event.get('event_type', '')).upper() == "SERVICE":
                        category = "danger"
                    
                    # We send the message AND the ID separated by a pipe |
                    flash(f"📅 {event['event_type']}: {event['title']} on {event['event_date']}", category)
                    
        except Exception as e:
            print(f"Error checking calendar: {e}")

# --- NEW ROUTE TO HANDLE THE DISMISS CLICK ---
@app.route("/dismiss-reminder/<event_id>")
def dismiss_reminder(event_id):
    if 'dismissed_reminders' not in session:
        session['dismissed_reminders'] = []
    
    # Add this ID to the "Don't show again" list for this session
    dismissed = session['dismissed_reminders']
    if event_id not in dismissed:
        dismissed.append(event_id)
        session['dismissed_reminders'] = dismissed
        session.modified = True 
        
    return "", 204 # Returns "No Content" - just tells the browser it's done

# --- 2. THE SAVING ROUTE ---
@app.route("/calendar/add", methods=["POST"])
def add_calendar_entry():
    # 1. Define the correct path
    DATA_DIR = "DATA"
    FILE_NAME = "calendar.csv"
    FILE_PATH = os.path.join(DATA_DIR, FILE_NAME)

    # 2. Ensure the DATA directory actually exists
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

    # 3. Get form data
    event_type = request.form.get("event_type")
    title = request.form.get("title", "").upper() # Upper case for truck regs
    event_date = request.form.get("event_date")
    
    if not event_date or not title:
        flash("Error: Title and Date are required.", "danger")
        return redirect(request.referrer or "/fuel")

  # 4. Create the entry with a Unique ID
    # We use a timestamp-based ID or check the current row count
    try:
        if os.path.exists(FILE_PATH) and os.path.getsize(FILE_PATH) > 0:
            existing_df = pd.read_csv(FILE_PATH)
            next_id = len(existing_df) + 1
        else:
            next_id = 1
    except:
        next_id = 1

    new_entry = {
        'id': next_id, # This adds the missing ID column
        'event_type': event_type,
        'title': title,
        'event_date': event_date,
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    try:
        df_new = pd.DataFrame([new_entry])
        
        # 5. Save logic
        # Check if file exists and has content to decide on headers
        file_exists = os.path.isfile(FILE_PATH) and os.path.getsize(FILE_PATH) > 0
        
        df_new.to_csv(FILE_PATH, mode='a', header=not file_exists, index=False)
        
        flash(f"Success: {title} scheduled for {event_date}", "success")
        print(f"DEBUG: Successfully wrote to {FILE_PATH}") # Check your terminal for this!

    except Exception as e:
        print(f"SAVE ERROR: {e}")
        flash(f"System Error: Could not write to CSV. {e}", "danger")
    
    return redirect(request.referrer or "/fuel")
#========================================OPEN ORDERS===========================================================

def get_outstanding_summary():
    data_frames = []
    
    # =========================================================
    # 1. PROCESS ENGEN ORDERS (orders.csv vs trips.csv)
    # =========================================================
    if os.path.exists("DATA/orders.csv"):
        try:
            engen_df = pd.read_csv("DATA/orders.csv", dtype=str)
            engen_df.columns = engen_df.columns.str.strip()
            
            # Clean string spaces from values aggressively
            engen_df = engen_df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)
            
            # Filter out allocated Engen orders if trips.csv exists
            if os.path.exists("DATA/trips.csv"):
                trips_df = pd.read_csv("DATA/trips.csv", dtype=str)
                trips_df.columns = trips_df.columns.str.strip()
                
                if 'order_number' in trips_df.columns:
                    allocated_engen = trips_df['order_number'].dropna().str.strip().unique()
                    
                    # Create matching keys handling potential leading-zero dropouts
                    engen_df['match_key'] = engen_df['order_number'].astype(str).str.strip()
                    allocated_set = set(allocated_engen) | {x.lstrip('0') for x in allocated_engen if x.strip()}
                    
                    engen_df = engen_df[
                        ~engen_df['match_key'].isin(allocated_set) & 
                        ~engen_df['match_key'].str.lstrip('0').isin(allocated_set)
                    ].copy()
                    engen_df = engen_df.drop(columns=['match_key'])

            if 'offloading_point' in engen_df.columns and 'product' in engen_df.columns:
                engen_clean = engen_df[['order_number', 'product', 'offloading_point']].copy()
                data_frames.append(engen_clean)
        except Exception as e:
            print(f"Error loading or filtering orders.csv: {e}")

    # =========================================================
    # 2. PROCESS PUMA ORDERS (puma_open_orders.csv vs puma_trips.csv)
    # =========================================================
    if os.path.exists("DATA/puma_open_orders.csv"):
        try:
            puma_df = pd.read_csv("DATA/puma_open_orders.csv", dtype=str)
            puma_df.columns = puma_df.columns.str.strip()
            
            # Clean string spaces from values aggressively
            puma_df = puma_df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)
            
            # Filter out allocated Puma orders if puma_trips.csv exists
            if os.path.exists("DATA/puma_trips.csv"):
                puma_trips_df = pd.read_csv("DATA/puma_trips.csv", dtype=str)
                puma_trips_df.columns = puma_trips_df.columns.str.strip()
                
                # Puma tracks its allocations via 'puma_order_number' or 'order_number'
                puma_trip_col = 'puma_order_number' if 'puma_order_number' in puma_trips_df.columns else 'order_number'
                
                if puma_trip_col in puma_trips_df.columns:
                    allocated_puma = puma_trips_df[puma_trip_col].dropna().str.strip().unique()
                    
                    puma_df['match_key'] = puma_df['puma_order_number'].astype(str).str.strip()
                    allocated_puma_set = set(allocated_puma) | {x.lstrip('0') for x in allocated_puma if x.strip()}
                    
                    puma_df = puma_df[
                        ~puma_df['match_key'].isin(allocated_puma_set) & 
                        ~puma_df['match_key'].str.lstrip('0').isin(allocated_puma_set)
                    ].copy()
                    puma_df = puma_df.drop(columns=['match_key'])

            # Normalize the data structure into common layout names
            puma_clean = pd.DataFrame()
            if 'puma_order_number' in puma_df.columns:
                puma_clean['order_number'] = puma_df['puma_order_number']
                
            if 'product' in puma_df.columns:
                puma_clean['product'] = puma_df['product']
                
            # Assigning a uniform location label since Puma lacks an offloading point column
            puma_clean['offloading_point'] = "PUMA REQUISITIONS"
            
            if not puma_clean.empty:
                data_frames.append(puma_clean)
        except Exception as e:
            print(f"Error loading or filtering puma_open_orders.csv: {e}")

    # Return empty layout early if no records found
    if not data_frames:
        return []

    # Combine both cleanly filtered datasets into one pool
    combined_orders = pd.concat(data_frames, ignore_index=True)
    if combined_orders.empty:
        return []

    # =========================================================
    # 3. PRODUCT RE-MAPPING & STANDARDIZATION
    # =========================================================
    def standardize_product(prod_name):
        if not isinstance(prod_name, str):
            return "UNKNOWN"
            
        prod_upper = prod_name.upper().strip()
        
        # Group all variation labels of standard Diesel down to 'ADO'
        if prod_upper in ['ADO', 'D50', 'DIESEL', 'D500']:
            return 'ADO'
            
        # Standardize ADO(CLP) variations
        if 'CLP' in prod_upper:
            return 'ADO(CLP)'
            
        # Standardize ULP variations
        if 'ULP' in prod_upper or '95' in prod_upper:
            return 'ULP95'
            
        # Standardize Paraffin/Illuminating Kerosene variations
        if prod_upper in ['IK', 'PARAFFIN']:
            return 'IK'
            
        return prod_upper

    combined_orders['product'] = combined_orders['product'].apply(standardize_product)

    # 4. Prepare for aggregation pivot
    combined_orders['count'] = 1
    
    # 5. Group by offloading_point and product layout matrices
    summary = combined_orders.pivot_table(
        index='offloading_point', 
        columns='product', 
        values='count', 
        aggfunc='sum', 
        fill_value=0
    )

    # 6. Format dictionary array for Jinja loop interface display
    data = []
    for col in ['ULP95', 'ADO', 'ADO(CLP)', 'IK']:
        if col not in summary.columns:
            summary[col] = 0
            
    for point, row in summary.iterrows():
        data.append({
            'name': point,
            'ulp95': int(row.get('ULP95', 0)),
            'ado': int(row.get('ADO', 0)),
            'adoCLP': int(row.get('ADO(CLP)', 0)),
            'ik': int(row.get('IK', 0)),
        })
        
    return data

import urllib.parse # Add this to the top of your app.py file

#--------------TRUCK UTILIZATION----------------------------------

def get_idle_fleet_stats():
    import pandas as pd
    from datetime import datetime
    import os

    try:
        # 1. Load and Clean Vehicles Base Registry
        if not os.path.exists("DATA/vehicles.csv"):
            return []
            
        vehicles_df = pd.read_csv("DATA/vehicles.csv")
        vehicles_df['truck_reg'] = vehicles_df['truck_reg'].astype(str).str.strip().str.upper()
        
        # Remove any potential registration duplication
        vehicles_df = vehicles_df.drop_duplicates(subset=['truck_reg'])

        # 2. Gather Data Across All Trip Repositories
        trip_files = ["DATA/trips.csv", "DATA/secondary_trips.csv", "DATA/puma_trips.csv"]
        all_trips_list = []

        for file_path in trip_files:
            if os.path.exists(file_path):
                try:
                    df_temp = pd.read_csv(file_path, dtype=str)
                    df_temp.columns = df_temp.columns.str.strip()
                    
                    # Normalize columns to standard 'truck_reg' and 'status' tags
                    rename_dict = {}
                    for col in df_temp.columns:
                        if col.strip().lower() in ['truck_reg', 'truck_registration', 'horse_reg']:
                            rename_dict[col] = 'truck_reg'
                        elif col.strip().lower() in ['status', 'trip_status']:
                            rename_dict[col] = 'status'
                    
                    if rename_dict:
                        df_temp = df_temp.rename(columns=rename_dict)
                        
                    if 'truck_reg' in df_temp.columns and 'status' in df_temp.columns:
                        all_trips_list.append(df_temp)
                except Exception as e:
                    print(f"Error parsing trip file {file_path}: {e}")

        # Combine all trips into a unified history master frame
        if all_trips_list:
            trips_df = pd.concat(all_trips_list, ignore_index=True)
            trips_df['truck_reg'] = trips_df['truck_reg'].astype(str).str.strip().str.upper()
            trips_df['status'] = trips_df['status'].astype(str).str.strip().str.upper()
        else:
            trips_df = pd.DataFrame(columns=['truck_reg', 'status', 'date_offloaded', 'offloading_time'])

        # 3. Process Fleet Breakdowns Registry 
        try:
            breakdowns_df = pd.read_csv("DATA/breakdowns.csv")
            breakdowns_df['truck_reg'] = breakdowns_df['truck_reg'].astype(str).str.strip().str.upper()
            breakdowns_df['status'] = breakdowns_df['status'].astype(str).str.strip().str.upper()
            active_breakdowns = breakdowns_df[breakdowns_df['status'] != 'REPAIRED']['truck_reg'].unique()
        except:
            active_breakdowns = []

        now = datetime.now()
        idle_trucks = []

        # 4. Identify Busy Trucks Across All Combined Services
        active_statuses = ['LOADING', 'IN TRANSIT', 'EN ROUTE','IN-TRANSIT','INTRANSIT']
        busy_trucks = trips_df[trips_df['status'].isin(active_statuses)]['truck_reg'].unique()

        # 5. Process the Vehicle Registry Fleet
        for _, vehicle in vehicles_df.iterrows():
            reg = vehicle['truck_reg']
            
            # Skip rows with invalid data
            if pd.isna(reg) or reg == 'NAN' or reg == '':
                continue

            # IF TRUCK IS ACTIVE ANYWHERE, IT IS NOT IDLE
            if reg in busy_trucks:
                continue

            # Determine breakdown condition
            on_breakdown = reg in active_breakdowns
            
            # Get last activity for calculation by pulling history from all combined logs
            completed_statuses = ['OFFLOADED', 'INVOICED', 'COMPLETED']
            truck_history = trips_df[
                (trips_df['truck_reg'] == reg) & 
                (trips_df['status'].isin(completed_statuses))
            ].copy()
            
            last_active = None
            
            if not truck_history.empty:
                # Standardize alternative date layout delimiters (- vs /)
                if 'date_offloaded' in truck_history.columns:
                    truck_history['date_offloaded'] = truck_history['date_offloaded'].astype(str).str.replace('-', '/')
                    
                    # Fallback sorting configuration block
                    offload_time_col = 'offloading_time' if 'offloading_time' in truck_history.columns else 'time_offloaded'
                    if offload_time_col not in truck_history.columns:
                        truck_history[offload_time_col] = '06:00'
                        
                    truck_history = truck_history.sort_values(by=['date_offloaded', offload_time_col], ascending=False)
                    
                    last_row = truck_history.iloc[0]
                    date_str = str(last_row['date_offloaded']).strip()
                    time_str = str(last_row.get(offload_time_col, '06:00')).strip()
                    
                    try:
                        last_active = datetime.strptime(f"{date_str} {time_str}", "%Y/%m/%d %H:%M")
                    except:
                        try:
                            last_active = datetime.strptime(date_str, "%Y/%m/%d")
                        except:
                            last_active = None

            # Fallback if no history matches or parsing error happens
            if last_active is None:
                last_active = now

            # Calculate Downtime Parameters
            diff = now - last_active
            days = diff.days
            hours = diff.seconds // 3600

            idle_trucks.append({
                'reg': reg,
                'status': 'BREAKDOWN' if on_breakdown else 'IDLE',
                'idle_time': f"{days}d {hours}h",
                'days_raw': days,
                'hours_raw': hours
            })

        # Sort with longest-idle items prioritizing breakdown statuses on top
        return sorted(idle_trucks, key=lambda x: (x['status'] == 'BREAKDOWN', x['days_raw'], x['hours_raw']), reverse=True)

    except Exception as e:
        print(f"Error compiling fleet statistics: {e}")
        return []
# In your dashboard route:
# idle_fleet = get_idle_fleet_stats()
# return render_template("dashboard.html", idle_fleet=idle_fleet, ...)
#==================================Calculator========================================
import math
import pandas as pd
from flask import Blueprint, request, jsonify

# Change this line from @fuel_calc_bp.route to @app.route
@app.route('/fuel-calculator')
def render_fuel_calculator():
    return render_template('calculator.html')

fuel_calc_bp = Blueprint('fuel_calc', __name__)
SECONDARY_CSV = 'data/secondary_trips.csv'

def calculate_vcf(density_15c, temperature_c):
    """
    Standard ASTM Table 60B formulation for specialized petroleum products (Diesel/Distillates).
    """
    if temperature_c == 15.0:
        return 1.0
    
    # Constants for Product Group B (Diesel / Fuel Oils)
    k0 = 186.9696
    k1 = 0.4862
    
    # Calculate thermal expansion coefficient (alpha)
    alpha = (k0 + k1 * density_15c) / (density_15c ** 2)
    
    delta_t = temperature_c - 15.0
    vcf = math.exp(-alpha * delta_t * (1.0 + 0.8 * alpha * delta_t))
    return round(vcf, 5)

@fuel_calc_bp.route('/api/compute-volume-correction', methods=['POST'])
def compute_volume_correction():
    data = request.get_json()
    
    try:
        litres_loaded = float(data.get('litres_loaded', 0))
        observed_temp = float(data.get('observed_temperature', 15.0))
        # Standard density for ADO/Diesel in southern Africa is roughly 0.835 @ 15°C
        base_density = float(data.get('base_density', 0.8350)) 
        
        # Run calculation
        vcf = calculate_vcf(base_density, observed_temp)
        corrected_litres = round(litres_loaded * vcf, 0)
        variance = corrected_litres - litres_loaded

        return jsonify({
            'status': 'Success',
            'vcf': vcf,
            'corrected_litres_at_15c': corrected_litres,
            'thermal_variance_litres': variance
        }), 200

    except Exception as e:
        return jsonify({'status': 'Error', 'message': str(e)}), 400


@app.route("/dashboard")
@login_required
def dashboard():
    auto_update_all_vehicle_km()
    TRIPS_PATH = "DATA/trips.csv"
    months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", 
              "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    
    chart_data = {}
    
    if os.path.exists(TRIPS_PATH):
        # 1. Load with Excel-proof encoding
        df_chart = pd.read_csv(TRIPS_PATH, encoding='utf-8-sig')
        df_chart.columns = df_chart.columns.str.strip()
        
        # 2. Clean locations and dates
        df_chart = df_chart.dropna(subset=['offloading_point', 'date_loaded'])
        df_chart['offloading_point'] = df_chart['offloading_point'].str.strip().str.upper()
        
        # 3. Handle dates as strings to avoid the "March Only" trap
        # This ensures April trips are counted even if the date format is messy
        df_chart['date_str'] = df_chart['date_loaded'].astype(str)
        
        # Filter for the year 2026 anywhere in the string
        df_chart = df_chart[df_chart['date_str'].str.contains("2026")]

        dynamic_locations = sorted(df_chart['offloading_point'].unique())

        for loc in dynamic_locations:
            counts = [0] * 12
            # Filter rows for this specific location
            loc_df = df_chart[df_chart['offloading_point'] == loc]
            
            for i in range(1, 13):
                # Look for the month number (01, 02, 03, 04...) in the date string
                month_pattern = f"-{i:02d}-" # Searches for "-04-"
                alt_pattern = f"/{i:02d}/"   # Searches for "/04/" (Excel style)
                
                month_mask = loc_df['date_str'].str.contains(month_pattern) | \
                             loc_df['date_str'].str.contains(alt_pattern)
                
                counts[i-1] = int(len(loc_df[month_mask]))
            
            chart_data[loc] = counts
    # ==========================================
    # 1. TIME & INITIALIZATION
    # ==========================================
    now = datetime.now()
    curr_month_str = now.strftime("%Y-%m")
    curr_year_str = now.strftime("%Y")
    
    # Metrics & Aggregates Initialization
    monthly_trips_data = [0] * 12
    monthly_revenue = [0] * 12
    monthly_expenses = [0] * 12
    locations = []
    rev_mtd, km_mtd, trips_mtd, fuel_mtd = 0, 0, 0, 0
    
    # ==========================================
    # 2. CORE DATA LOADING (CSV/FILE ACCESS)
    # ==========================================
    vehicles = load_vehicles()
    trips = load_trips()
    fuel = load_fuel()
    breakdowns = load_breakdowns()
    incidents_list = load_incidents()
   
    # Call the helper! No more AttributeError.
    df = get_allowance_df()
    
    # Now this works perfectly
    allowances = df.to_dict(orient='records')
    df_bto = get_bto_registry()
    df_trips = pd.read_csv('DATA/trips.csv')
    records = load_working_hours()
    
    try:
        compliance_data = pd.read_csv('DATA/compliance.csv').to_dict('records')
    except:
        compliance_data = []

    # ==========================================
    # 3. FATIGUE, HOURS & HR CALCULATIONS
    # ==========================================
    enriched = enrich_records(records) # Calculates hours_worked
    total_work_hours = 0
    for r in enriched:
        r_date_str = str(r.get('date', ''))
        if r_date_str.startswith(now.strftime('%Y-%m')):
            total_work_hours += float(r.get('hours_worked', 0))
    
    df_hours = pd.DataFrame() # Defensive Loading
    active_drivers_count = 0
    violation_count = 0
    fatigue_alerts = []

    if not df_hours.empty:
        df_clean = df_hours.dropna(subset=['date'])
        this_month_df = df_clean[
            (df_clean['date'].dt.month == now.month) & 
            (df_clean['date'].dt.year == now.year)
        ].copy()
        
        if 'driver' in this_month_df.columns:
            active_drivers_count = this_month_df['driver'].nunique()
        
        if 'violation' in this_month_df.columns:
            violation_count = len(this_month_df[this_month_df['violation'].astype(str).str.lower() == 'true'])

        if 'driver' in df_clean.columns and 'off_day' in df_clean.columns:
            for driver in df_clean['driver'].unique():
                driver_data = df_clean[df_clean['driver'] == driver].sort_values('date', ascending=False)
                consecutive_days = 0
                for _, row in driver_data.iterrows():
                    if str(row.get('off_day', 'no')).lower() == 'no':
                        consecutive_days += 1
                    else:
                        break
                if consecutive_days >= 12:
                    fatigue_alerts.append({
                        'name': driver,
                        'days_at_work': consecutive_days,
                        'wa_link': f"https://wa.me/?text=Fatigue%20Alert:%20{driver}%20has%20worked%20{consecutive_days}%20days."
                    })

    # ==========================================
    # 4. TRIP & REVENUE PROCESSING (Annual & MTD)
    # ==========================================
    for t in trips:
        date_str = str(t.get("date_loaded", ""))
        if date_str.startswith(curr_year_str):
            try:
                m = int(date_str[5:7]) - 1
                val = float(t.get("amount", 0) or 0)
                if 0 <= m <= 11:
                    monthly_trips_data[m] += 1
                    monthly_revenue[m] += val
                
                if date_str.startswith(curr_month_str) and str(t.get("position", "")).strip().upper() == "COMPLETED":
                    trips_mtd += 1
                    # Note: rev_mtd is recalculated in section 5 via rates merge
                    km_mtd += float(t.get("km_travelled", 0) or 0)
            except: 
                continue

    # ==========================================
    # 5. FINANCE & RATES CALCULATIONS
    # ==========================================
    try:
        df_rates = pd.read_csv('DATA/rates.csv')
        for col in ['customer', 'loading_point', 'offloading_point']:
            df_rates[col] = df_rates[col].astype(str).str.strip().str.upper()
            df_trips[col + '_clean'] = df_trips[col].astype(str).str.strip().str.upper()
            
        df = pd.merge(
            df_trips, df_rates, 
            left_on=['customer_clean', 'loading_point_clean', 'offloading_point_clean'],
            right_on=['customer', 'loading_point', 'offloading_point'],
            how='left', suffixes=('', '_r')
        )
    except:
        df = df_trips
        df['rate_per_litre'] = 0

    df['litres_offloaded'] = pd.to_numeric(df['litres_offloaded'], errors='coerce').fillna(0)
    df['rate_per_litre'] = df['rate_per_litre'].fillna(0.0)
    df['amount'] = df['litres_offloaded'] * df['rate_per_litre']

    rev_mtd = 0 # Final calculation for MTD Revenue
    curr_month_str_finance = datetime.now().strftime('%Y-%m') 
    for _, row in df.iterrows():
        date_str = str(row.get('date_loaded', ""))
        if date_str.startswith(curr_month_str_finance):
            rev_mtd += row['amount']

    # ==========================================
    # 6. EXPENSES (FUEL) & FLEET STATUS
    # ==========================================
    for f in fuel:
        date_str = str(f.get("date", ""))
        if date_str.startswith(curr_year_str):
            try:
                m = int(date_str[5:7]) - 1
                cost = float(f.get("cost", 0) or 0)
                if 0 <= m <= 11:
                    monthly_expenses[m] += cost
                if date_str.startswith(curr_month_str):
                    fuel_mtd += float(f.get("litres", 0) or 0)
            except: continue

    active_trucks = len([t for t in trips if t.get("status", "") == "IN TRANSIT"])
    
    in_transit = len([t for t in trips if t.get("status", "").lower() == "in transit"])
    pending_allowance = len([a for a in allowances if a.get("allowance_status", "").lower() == "pending"])
    active_breakdowns = len([
        b for b in breakdowns 
        if b.get("status", "").lower() not in ["resolved", "fixed", "repaired", "completed"]
    ])
    inactive_trucks = len([d for d in vehicles]) - active_trucks 
    
   

    offloading_groups = {}
    
    # Base directory path setup where your CSVs live
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # -------------------------------------------------------------------------
    # 1. PROCESS SECONDARY LOCAL MULTI-DROP TRIPS -> AGGREGATED UNIQUE TRIPS ONCE
    # -------------------------------------------------------------------------
    secondary_path = os.path.join(base_dir, 'DATA/secondary_trips.csv')
    if os.path.exists(secondary_path):
        try:
            df_secondary = pd.read_csv(secondary_path).drop_duplicates()
            secondary_list = df_secondary.to_dict('records')
            
            # Temporary storage to consolidate duplicate trip_ids for local distribution
            local_trips_aggregation = {}
            
            for t in secondary_list:
                status = str(t.get("status", "")).upper().strip()
                if status in ["IN TRANSIT", "LOADING"]:
                    trip_id = str(t.get("trip_id", "")).strip()
                    product = str(t.get("product", "")).strip()
                    
                    if not trip_id:
                        continue
                        
                    if trip_id not in local_trips_aggregation:
                        # Initialize tracking entry for this unique trip layout
                        local_trips_aggregation[trip_id] = {
                            'truck': t.get('truck_reg'),
                            'driver': t.get('driver'),
                            'products_set': {product} if product else set(),
                            'status': t.get('status'),
                            'trip_type': 'SECONDARY'
                        }
                    else:
                        # If trip_id is already present, just accumulate the new product type
                        if product:
                            local_trips_aggregation[trip_id]['products_set'].add(product)

            # Assign a single master card key for all local operations
            card_key = "LOCAL DELIVERIES"
            if local_trips_aggregation:
                offloading_groups[card_key] = []
                
                for trip_id, data in local_trips_aggregation.items():
                    # Safely convert the set of unique products into an alphabetical slash-separated string
                    # e.g., "ADO (Diesel)/ULP 95" or "ULP 95/IK (Paraffin)"
                    sorted_products = sorted(list(data['products_set']))
                    combined_products = "/".join(sorted_products) if sorted_products else "---"
                    
                    offloading_groups[card_key].append({
                        'truck': data['truck'],
                        'driver': data['driver'],
                        'product': combined_products,  # <--- Clean slash separation output
                        'status': data['status'],
                        'trip_type': 'SECONDARY'
                    })
        except Exception as e:
            print(f"Error loading secondary_trips.csv: {e}")

    # -------------------------------------------------------------------------
    # 2. PROCESS PUMA LOGISTICS TRIPS -> SEPARATE CARD PER DESTINATION
    # -------------------------------------------------------------------------
    puma_path = os.path.join(base_dir, 'DATA/puma_trips.csv')
    if os.path.exists(puma_path):
        try:
            df_puma = pd.read_csv(puma_path).drop_duplicates()
            puma_list = df_puma.to_dict('records')
            
            for t in puma_list:
                status = str(t.get("status", "")).upper().strip()
                if status in ["IN TRANSIT", "LOADING","IN-TRANSIT"]:
                    point = str(t.get("destination", "Unknown")).strip().upper()
                    if point not in offloading_groups:
                        offloading_groups[point] = []
                    offloading_groups[point].append({
                        'truck': t.get('truck_reg'),
                        'driver': t.get('driver_name'),
                        'product': t.get('product'),
                        'status': t.get('status'),
                        'trip_type': 'PUMA'
                    })
        except Exception as e:
            print(f"Error loading puma_trips.csv: {e}")

    # -------------------------------------------------------------------------
    # 3. PROCESS ENGEN BRIDGING TRIPS -> SEPARATE CARD PER DESTINATION
    # -------------------------------------------------------------------------
    engen_path = os.path.join(base_dir, 'DATA/trips.csv')
    if os.path.exists(engen_path):
        try:
            df_engen = pd.read_csv(engen_path).drop_duplicates()
            engen_list = df_engen.to_dict('records')
            
            for t in engen_list:
                status = str(t.get("status", t.get("trip_status", ""))).upper().strip()
                if status in ["IN TRANSIT", "LOADING"]:
                    point = str(t.get("offloading_point", t.get("offload_point", "Unknown"))).strip().upper()
                    if point not in offloading_groups:
                        offloading_groups[point] = []
                    offloading_groups[point].append({
                        'truck': t.get('truck_reg') or t.get('horse_reg'),
                        'driver': t.get('driver') or t.get('driver_assignment'),
                        'product': t.get('product') or t.get('product_group'),
                        'status': t.get('status') or t.get('trip_status'),
                        'trip_type': 'ENGEN'
                    })
        except Exception as e:
            print(f"Error loading trips.csv: {e}")

    

    # ==========================================
    # 8. ALERTS: COMPLIANCE, ROSTER & SERVICE
    # ==========================================
    alerts = {"truck_docs": [], "fatigue_home": [], "driver_docs": []}
    
    # Truck Compliance
    for row in compliance_data:
        expiry_str = row.get('expiry_date', '')
        if expiry_str:
            try:
                expiry_date = datetime.strptime(expiry_str, '%Y-%m-%d')
                days_left = (expiry_date - now).days
                if days_left <= 30:
                    alerts["truck_docs"].append({
                        "unit": row.get('unit_id', 'Unknown'), 
                        "doc": row.get('name', 'Document'), 
                        "date": expiry_str,
                        "days": days_left
                    })
            except: continue
    alerts["truck_docs"].sort(key=lambda x: x['days'])

    # Driver Compliance (BTO)
    try:
        df_bto = get_bto_registry()
        date_cols = [col for col in df_bto.columns if any(x in col for x in ['Date', 'Exp', 'procedure'])]
        for _, row in df_bto.iterrows():
            d_name = row.get('NAME/SURNAME', 'Unknown Driver')
            for col in date_cols:
                date_val = row.get(col, '')
                if date_val and str(date_val) != 'nan' and date_val != '':
                    try:
                        exp_date = datetime.strptime(str(date_val), '%Y-%m-%d')
                        days_left = (exp_date - now).days
                        if days_left <= 60:
                            alerts["driver_docs"].append({
                                "name": d_name, "doc_type": col, "date": str(date_val), "days": days_left
                            })
                    except: continue
        alerts["driver_docs"].sort(key=lambda x: x['days'])
    except Exception as e:
        print(f"BTO Error: {e}")

    # Roster/Home Leave
    try:
        roster_list = process_roster_data('DATA/roster.csv')
        for item in roster_list:
            if item.get('status') == "Due for Home":
                d_name = item.get('driver', 'Driver')
                phone = str(item.get('phone_number', '')) 
                msg = f"Hello {d_name}, You are scheduled to to leave on the next batch."
                wa_url = f"whatsapp://send?phone={phone}&text={urllib.parse.quote(msg)}"
                alerts["fatigue_home"].append({
                    "name": d_name,
                    "days_at_work": item.get('number_of_days_at_work', 0),
                    "wa_link": wa_url
                })
    except: pass

    # Service Alerts
    service_alerts = []
    for v in vehicles:
        status, km_to_service = calculate_service_status(v)
        if km_to_service <= 2000:
            service_alerts.append({
                'reg': v.get('truck_reg'),
                'km_to_go': km_to_service,
                'status': status,
                'last_update': v.get('last_km_update', 'Never')
            })
    outstanding_summary = get_outstanding_summary()
    # ==========================================
    # 9. FINAL STATS ASSEMBLY & RENDER
    # ==========================================
    stats = {
        'work_hours_mtd': round(total_work_hours, 1),
        'active_drivers': active_drivers_count,
        'incidents_mtd': violation_count,
        "active_trucks": active_trucks,
        "inactive_trucks": inactive_trucks,
        "in_transit": in_transit,
        "pending_allowance": pending_allowance,
        "active_breakdowns": active_breakdowns,
        "revenue_mtd": rev_mtd,
        "fuel_mtd": fuel_mtd,
        "km_mtd": km_mtd,
        "trips_mtd": trips_mtd,
        'service_alerts': service_alerts
    }
    csv_path = 'DATA/trips.csv'
    mtd_litres = 0

    if os.path.exists(csv_path):
        try:
            
            # FIX 1: Use utf-8-sig to ignore hidden Excel characters
            df = pd.read_csv(csv_path, encoding='utf-8-sig')
            
            # Clean headers to remove hidden spaces Excel might have added
            df.columns = df.columns.str.strip()
            
            # FIX 2: Better date parsing. dayfirst=True helps if Excel flipped the date format.
            # errors='coerce' is good, it keeps 'IN TRANSIT' from crashing the code.
            # Removing dayfirst=True to stop the conflict with YYYY/MM/DD
            # 1. Clean the date column and turn everything into a string
            df['date_offloaded'] = df['date_offloaded'].astype(str)

            # 2. Get the current Year and Month as strings
            now = datetime.now()
            curr_year = str(now.year)        # "2026"
            curr_month = now.strftime('%m')  # "04"

            # 3. Create a mask that looks for "2026" AND "04" anywhere in the text
            # This catches 2026/04/01, 01/04/2026, and 2026-04-01
            mask = df['date_offloaded'].str.contains(curr_year) & \
                df['date_offloaded'].str.contains(curr_month)

            mtd_data = df[mask].copy()
           
            # FIX 4: Convert to numeric BEFORE summing
            # Sometimes Excel saves numbers as "10 000" (with a space) which kills the sum.
            if not mtd_data.empty:
                # We strip any potential spaces from strings before converting to numbers
                if mtd_data['litres_offloaded'].dtype == object:
                    mtd_data['litres_offloaded'] = mtd_data['litres_offloaded'].str.replace(' ', '').str.replace(',', '')
                
                mtd_litres = pd.to_numeric(mtd_data['litres_offloaded'], errors='coerce').fillna(0).sum()
            
        except Exception as e:
            # Flash the error so you can see exactly what column or row is breaking it
            flash(f"Error reading trips.csv: {e}", "danger")
    
    idle_fleet_data = get_idle_fleet_stats()
    
    return render_template(
        "dashboard.html",
        stats=stats,
        alerts=alerts,
        incidents=incidents_list,
        monthly_trips_data=monthly_trips_data,
        monthly_revenue=monthly_revenue,
        monthly_expenses=monthly_expenses,
        locations=locations,
        now=now,
        offloading_groups=offloading_groups,
        fatigue_alerts=fatigue_alerts,
        outstanding_summary=outstanding_summary,
        mtd_litres=mtd_litres,
        chart_data=chart_data, # This is the key dictionary
        months=months,
        idle_fleet=idle_fleet_data
    )


#=======================================PUMA=================================================
@app.route('/puma-ops')
@login_required
def puma_ops():
    # 1. Load Drivers and Vehicles (with clean duplication handling)
    drivers_df = pd.read_csv('DATA/bto_registry.csv').drop_duplicates(subset=['NAME/SURNAME']).fillna('')
    drivers_list = drivers_df['NAME/SURNAME'].tolist()

    vehicles_df = pd.read_csv('DATA/vehicles.csv').drop_duplicates(subset=['truck_reg']).fillna('')
    truck_map = vehicles_df.set_index('truck_reg')['trailer_reg'].to_dict()
    truck_list = vehicles_df['truck_reg'].tolist()

    # 2. Get raw open orders data
    open_orders_df = pd.read_csv(os.path.join(DATA_DIR, 'puma_open_orders.csv'), dtype=str).fillna('')
    
    if 'status' in open_orders_df.columns:
        open_orders_df['status'] = open_orders_df['status'].str.strip().str.upper()
    else:
        open_orders_df['status'] = 'OPEN'

    used_order_numbers = set()
    trips_filepath = os.path.join(DATA_DIR, 'puma_trips.csv')
    
    trips_list = []
    df_trips = pd.DataFrame()
    
    if os.path.exists(trips_filepath):
        try:
            df_trips = pd.read_csv(trips_filepath, dtype=str).fillna('')
            df_trips.columns = [c.strip() for c in df_trips.columns]
            
            if 'puma_order_number' in df_trips.columns:
                used_order_numbers = set(df_trips['puma_order_number'].str.strip().tolist())
                
            for record in df_trips.to_dict('records'):
                raw_status = record.get('status', '').strip().upper()
                
                # Dynamic Sync: if invoiced column is set to 'Y', ensure status respects it
                if record.get('invoiced', '').strip().upper() == 'Y':
                    record['status'] = 'INVOICED'
                elif not raw_status or raw_status == '':
                    record['status'] = 'IN-TRANSIT'
                else:
                    record['status'] = raw_status
                    
                trips_list.append(record)
                
        except Exception as e:
            print(f"Error reading used orders tracking context: {e}")

    # Filter open orders so assigned entries are excluded cleanly
    open_orders = []
    for record in open_orders_df.to_dict('records'):
        order_num = str(record.get('puma_order_number', '')).strip()
        status_val = str(record.get('status', 'OPEN')).strip().upper()
        
        if status_val == 'OPEN' and order_num and order_num not in used_order_numbers:
            open_orders.append(record)

    # 3. COMPUTE MONTH-ON-MONTH KPIs (Aligned with YYYY-MM formatting for your layout template)
    monthly_kpis = defaultdict(lambda: {
        'delivered_vol': 0,
        'total_km': 0,
        'completed_orders': 0,
        'intransit_d50': 0,
        'intransit_ulp': 0
    })

    if not df_trips.empty:
        for _, row in df_trips.iterrows():
            # Get the date string and sanitize slashes to hyphens instantly
            date_str = str(row.get('loading_date', '')).strip() or str(row.get('order_release_date', '')).strip()
            date_str = date_str.replace('/', '-')
            
            month_key = "2026-06"  # Safe programmatic default fallback
            
            if date_str and date_str != '---':
                # Safely extract YYYY-MM from the text string structure
                parts = date_str.split()[0].split('-')
                if len(parts) >= 2 and len(parts[0]) == 4 and len(parts[1]) == 2:
                    month_key = f"{parts[0]}-{parts[1]}"

            try:
                offload_vol = int(float(row.get('offloaded_lits', 0) or 0))
            except ValueError:
                offload_vol = 0

            try:
                load_km = float(row.get('loading_km') or row.get('Loading KM') or 0)
                off_km = float(row.get('offloading_km') or row.get('Offloading KM') or 0)
                delta_km = max(0.0, off_km - load_km)
            except ValueError:
                delta_km = 0.0

            # Aggregate monthly variables smoothly into the matching HTML template indices
            monthly_kpis[month_key]['delivered_vol'] += offload_vol
            monthly_kpis[month_key]['total_km'] += int(delta_km)

    # 4. STATS RENDERING BINDINGS
    stats = {
        'planned': len(open_orders),
        'loaded_count': len([t for t in trips_list if t.get('status') != 'CANCELLED'])
    }
    auto_update_all_vehicle_km()
    return render_template(
        'trips/puma_trips.html', 
        trips=trips_list, 
        open_orders=open_orders, 
        drivers=drivers_list, 
        trucks=truck_list, 
        truck_map=truck_map, 
        monthly_kpis=dict(monthly_kpis), 
        stats=stats
    )

PUMA_ORDERS_CSV = 'data/puma_open_orders.csv'
PUMA_TRIPS_CSV = 'data/puma_trips.csv'

def read_csv_safe(path, default_cols):
    if not os.path.exists(path):
        return pd.DataFrame(columns=default_cols)
    return pd.read_csv(path).drop_duplicates()

@app.route('/puma-orders')
def puma_orders_dashboard():
    orders_df = read_csv_safe(PUMA_ORDERS_CSV, ['puma_order_number', 'product', 'loading_point', 'status'])
    trips_df = read_csv_safe(PUMA_TRIPS_CSV, ['puma_order_number', 'trip_id'])
    
    orders_df['puma_order_number'] = orders_df['puma_order_number'].astype(str).str.strip()
    trips_df['puma_order_number'] = trips_df['puma_order_number'].astype(str).str.strip()
    
    loaded_order_numbers = set(trips_df['puma_order_number'].tolist())
    
    processed_orders = []
    for _, row in orders_df.iterrows():
        order_num = row['puma_order_number']
        current_status = str(row['status']).upper().strip()
        
        if order_num in loaded_order_numbers or current_status == 'LOADED':
            continue  # Exclude loaded orders entirely
            
        processed_orders.append({
            'puma_order_number': order_num,
            'product': row['product'],
            'loading_point': row['loading_point'],
            'status': current_status
        })
        
    return render_template('puma_orders.html', orders=processed_orders)




@app.route('/api/cancel-puma-orders', methods=['POST'])
def cancel_puma_orders():
    data = request.get_json()
    order_numbers = data.get('order_numbers', [])
    
    if not order_numbers:
        return jsonify({'status': 'Error', 'message': 'No orders selected for cancellation.'}), 400

    # Ensure everything matches as string strings
    order_numbers = [str(num).strip() for num in order_numbers]

    if os.path.exists(PUMA_ORDERS_CSV):
        df = pd.read_csv(PUMA_ORDERS_CSV)
        df['puma_order_number'] = df['puma_order_number'].astype(str).str.strip()
        
        # Update matching rows to CANCELLED status
        df.loc[df['puma_order_number'].isin(order_numbers), 'status'] = 'CANCELLED'
        df.to_csv(PUMA_ORDERS_CSV, index=False)
        
        return jsonify({'status': 'Success', 'message': f'Successfully updated {len(order_numbers)} orders to CANCELLED.'}), 200
    
    return jsonify({'status': 'Error', 'message': 'Orders database flatfile missing.'}), 404

@app.route('/api/reactivate-puma-orders', methods=['POST'])
@login_required
def api_reactivate_puma_orders():
    try:
        data = request.get_json() or {}
        order_numbers = data.get('order_numbers', [])
        
        if not order_numbers:
            return jsonify({'status': 'Error', 'message': 'No order numbers provided'}), 400

        # Ensure order numbers are checked as strings
        order_numbers = [str(num).strip() for num in order_numbers]
        
        filepath = os.path.join(DATA_DIR, 'puma_open_orders.csv')
        if not os.path.exists(filepath):
            return jsonify({'status': 'Error', 'message': 'Source data file not found'}), 404

        # Read the open orders csv file
        df = pd.read_csv(filepath, dtype=str).fillna('')
        
        # Ensure a clean status column exists
        if 'status' not in df.columns:
            df['status'] = 'OPEN'
            
        # Clean up column tracking variants
        df['puma_order_number'] = df['puma_order_number'].astype(str).str.strip()
        
        # Change matched rows back to OPEN status
        mask = df['puma_order_number'].isin(order_numbers)
        if mask.any():
            df.loc[mask, 'status'] = 'OPEN'
            # Save the clean tracking matrix back down to storage
            df.to_csv(filepath, index=False)
            return jsonify({'status': 'Success', 'message': f'{len(order_numbers)} orders successfully reactivated.'})
        else:
            return jsonify({'status': 'Error', 'message': 'No matching order numbers found in registry.'}), 404

    except Exception as e:
        print(f"Operational failure updating database during reactivation: {e}")
        return jsonify({'status': 'Error', 'message': str(e)}), 500

@app.route('/create-puma-order', methods=['POST'])
@login_required
def create_puma_order():
 
    
    filepath = os.path.join(DATA_DIR, 'puma_trips.csv')

    data = request.form.to_dict()
    action = request.form.get('action') 

    order_number = data.get('puma_order_number', '').strip()

    # NEW: Strict Validation Boundary Check
    if not order_number:
        flash("❌ Error: Puma Order Number cannot be blank.", "danger")
        return redirect(url_for('puma_ops'))

    headers = [
        'driver_name', 'truck_reg', 'trailer_reg', 'puma_order_number', 
        'purchase_order_number', 'supplier_order_number', 'product', 
        'load_point', 'slot_booked', 'slot_number', 'order_release_date', 
        'report_date_loading', 'loading_date', 'departure_date_loading', 
        'current_position', 'comments', 'arrival_border_1', 'departure_border_1', 
        'arrival_border_2', 'departure_border_2', 'arrival_delivery_site', 
        'offload_date', 'discharge_point', 'loaded_lits', 'offloaded_lits', 
        'loss_gain', 'pod_submitted', 'submission_date', 'invoiced',
        'destination_country', 'loading_km', 'offloading_km', 'status' # <--- ADD THESE
    ]

    try:
        # Load existing trips to check against duplication loops
        if os.path.exists(filepath):
            df = pd.read_csv(filepath, dtype=str).fillna('')
            df.columns = [c.strip() for c in df.columns]
        else:
            df = pd.DataFrame(columns=headers)

        # NEW: Check if this order code already occupies a data record row instance
        if 'puma_order_number' in df.columns:
            df['puma_order_number'] = df['puma_order_number'].astype(str).str.strip()
            if order_number in df['puma_order_number'].values:
                flash(f"❌ Rejected: Order {order_number} has already been assigned and loaded before.", "danger")
                return redirect(url_for('puma_ops'))

        # Calculate Loss/Gain logic remains the same
        loaded = float(data.get('loaded_lits') or 0)
        offloaded = float(data.get('offloaded_lits') or 0)
        data['loss_gain'] = str(offloaded - loaded) # Force this calculation to a string format

        # FIXED: Wrap data.get(h, '') inside str() to guarantee safe string manipulation 
        new_row = {h: str(data.get(h, '')).strip() for h in headers}
        new_df = pd.DataFrame([new_row])
        df = pd.concat([df, new_df], ignore_index=True)
        
        # Save to CSV
        df.to_csv(filepath, index=False, encoding='utf-8')
        flash(f"Order {order_number} saved successfully!", "success")

        # Redirect to PDF Generation if requested
        if action == 'generate_pdf':
            return redirect(url_for('generate_loading_advice', order_no=order_number))
        
    except PermissionError:
        flash("Excel has the file locked. Close it to save.", "danger")
    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
    auto_update_all_vehicle_km()
    return redirect(url_for('puma_ops'))


@app.route('/generate-loading-advice/<order_no>')
@login_required
def generate_loading_advice(order_no):
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = os.path.join(PROJECT_ROOT, 'DATA')

    try:
        # Load Files
        tankers = pd.read_csv(os.path.join(DATA_DIR, 'tankers.csv'), dtype=str)
        puma_df = pd.read_csv(os.path.join(DATA_DIR, 'puma_trips.csv'), dtype=str)
        engen_df = pd.read_csv(os.path.join(DATA_DIR, 'trips.csv'), dtype=str)
        registry_df = pd.read_csv(os.path.join(DATA_DIR, 'bto_registry.csv'), dtype=str).fillna('')

        # Standardize headers
        for df in [tankers, puma_df, engen_df, registry_df]:
            df.columns = [str(c).strip().lower() for c in df.columns]

        # 1. Identify Source and Data
        trip = None
        source = None
        
        if order_no in puma_df['puma_order_number'].values:
            trip = puma_df[puma_df['puma_order_number'] == order_no].iloc[0]
            source = 'PUMA'
        elif order_no in engen_df['order_number'].values:
            trip = engen_df[engen_df['order_number'] == order_no].iloc[0]
            source = 'ENGEN'
        else:
            flash(f"Order {order_no} not found.", "danger")
            return redirect(url_for('puma_ops'))

        # 2. Extract Data based on Source
        driver_name = str(trip.get('driver_name' if source == 'PUMA' else 'driver', '')).strip()
        customer = 'PUMA ENERGY' if source == 'PUMA' else trip.get('customer', 'ENGEN')
        product = str(trip.get('product', 'ULP95')).upper()
        truck = trip.get('truck_reg', 'N/A')
        trailer = str(trip.get('trailer_reg', 'N/A')).strip()
        loading_point = trip.get('load_point' if source == 'PUMA' else 'loading_point', 'TERMINAL')

        # 3. Registry Lookup
        passport_number = "N/A"
        if 'name/surname' in registry_df.columns and 'passport_number' in registry_df.columns:
            # Ensure name column is strings before processing
            registry_df['clean_name'] = registry_df['name/surname'].astype(str).str.strip().str.lower()
            matches = registry_df[registry_df['clean_name'] == driver_name.lower()]
            if not matches.empty:
                passport_number = str(matches['passport_number'].iloc[0]).strip() or "N/A"

        # 4. Compartments and Seals
        target_suffix = '_ado' if any(x in product for x in ['D50', 'ADO']) else ('_ik' if 'IK' in product else '_ulp')
        
        tankers['reg_clean'] = tankers['trailer_reg'].astype(str).str.strip().str.lower()
        tanker_data = tankers[tankers['reg_clean'] == trailer.lower()]
        
        compartments = []
        # Initialize seal values
        seals = {'number': '0', 'box': 'N/A', 'top': 'N/A', 'manifold': 'N/A', 'transfer': 'N/A'}
        
        if not tanker_data.empty:
            row = tanker_data.iloc[0]
            # Get compartments
            for i in range(1, 10):
                col = f"cpt_{i}{target_suffix}"
                if col in row:
                    val = str(row[col])
                    liters = ''.join(filter(str.isdigit, val))
                    if liters and int(liters) > 0:
                        compartments.append({'number': i, 'liters': int(liters)})
            
            # Extract Seal Data
            seals = {
                'number': row.get('number_seals', '0'),
                'box': row.get('box', 'N/A'),
                'top': row.get('top', 'N/A'),
                'manifold': row.get('manifold', 'N/A'),
                'transfer': row.get('transfer_line', 'N/A')
            }
        

        # 5. PDF Generation
        context = {
            'company_name': 'HIPPO TRANSPORT',
            'date': datetime.now().strftime('%d/%m/%Y'),
            'order_no': order_no,
            'driver': driver_name,
            'passport_number': passport_number,
            'truck': truck,
            'trailer': trailer,
            'product': product,
            'loading_point': loading_point,
            'customer': customer,
            'compartments': compartments,
            'seals': seals,
            'logo_path': os.path.join(PROJECT_ROOT, 'static', 'images', 'logo.png').replace('\\', '/')
        }

        html_content = render_template('loading_advice_pdf.html', **context)
        config = pdfkit.configuration(wkhtmltopdf=r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe')
        options = {
                    'page-size': 'A4',
                    'margin-top': '0',
                    'margin-bottom': '0',
                    'margin-left': '0',
                    'margin-right': '0',
                    'enable-local-file-access': True,
                    'quiet': '',
                    'disable-smart-shrinking': '', # Often causes slow rendering
                    'no-stop-slow-scripts': '',
                    'load-error-handling': 'ignore', # Don't wait for missing assets
                    'load-media-error-handling': 'ignore'
                }
        
        # Use the dynamic configuration:
        pdf = pdfkit.from_string(
            html_content, 
            False, 
            configuration=config, 
            options=options
        )
        
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename=Loading_Advice_{order_no}.pdf'
        return response

    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('puma_ops'))
    
@app.route('/update-puma-order', methods=['POST'])
@login_required
def update_puma_order():
    import pandas as pd
    data = request.form.to_dict()
    order_id = data.get('puma_order_number') or data.get('puma_order_number_fallback')
    print(order_id)
    try:
        # 1. Load the current data
        df = pd.read_csv(PUMA_TRIPS_CSV, dtype=str).fillna('')

        # 2. Find the row index where the order number matches
        if order_id in df['puma_order_number'].values:
            idx = df.index[df['puma_order_number'] == order_id][0]

            # 3. Recalculate loss/gain for the update
            try:
                loaded = float(data.get('loaded_lits') or 0)
                offloaded = float(data.get('offloaded_lits') or 0)
                data['loss_gain'] = str(offloaded - loaded)
            except:
                data['loss_gain'] = "0"

            # 4. Automated Status Workflow Logic
            form_invoiced = data.get('invoiced', '').strip().upper()
            form_pod = data.get('pod_submitted', '').strip().upper()

            # Rule: Default to IN-TRANSIT, promote to DELIVERED if POD is Y, or INVOICED if Invoiced is Y
            if form_invoiced == 'Y':
                form_status = 'INVOICED'
            elif form_pod == 'Y':
                form_status = 'DELIVERED'
            else:
                form_status = 'IN-TRANSIT'

            # Force the workflow status into the data payload before writing
            data['status'] = form_status

            # 5. Update the specific row
            for key in data:
                if key in df.columns:
                    df.at[idx, key] = data[key]

            # 6. Save back to CSV
            df.to_csv(PUMA_TRIPS_CSV, index=False, encoding='utf-8')
            flash(f"Order {order_id} updated successfully! Status set to '{df.at[idx, 'status']}'.", "success")
        else:
            flash("Order not found for update.", "warning")

    except PermissionError:
        flash("Close the CSV in Excel and try again.", "danger")
    except Exception as e:
        flash(f"Update Error: {str(e)}", "danger")

    return redirect(url_for('puma_ops'))



@app.route('/puma-trips')
def puma_trips_route():
    # --- STEP 1: LOAD RELEVANT DATA FILES SAFELY ---
    # Load your core rosters/registries (Ensure these match your exact file names)
    try:
        vehicles_df = pd.read_csv('DATA/vehicles.csv')
        # Remove duplicates to ensure clean dropdown lists
        all_trucks = vehicles_df['truck_reg'].dropna().drop_duplicates().tolist()
    except Exception:
        all_trucks = []

    try:
        registry_df = pd.read_csv('DATA/bto_registry.csv')
        # Remove duplicates to ensure clean dropdown lists
        all_drivers = registry_df['driver_name'].dropna().drop_duplicates().tolist()
    except Exception:
        all_drivers = []

    # Load the 3 trip files to check who is busy
    try: engen_df = pd.read_csv('trips.csv')
    except Exception: engen_df = pd.DataFrame()

    try: secondary_df = pd.read_csv('secondary_trips.csv')
    except Exception: secondary_df = pd.DataFrame()

    try: puma_df = pd.read_csv('puma_trips.csv')
    except Exception: puma_df = pd.DataFrame()

    # --- STEP 2: IDENTIFY BUSY TRUCKS & DRIVERS (IN TRANSIT) ---
    busy_trucks = set()
    busy_drivers = set()

    # Helper function to find active elements with missing/invalid offload dates
    def extract_busy_units(df):
        if df.empty:
            return
        # Find rows where offload_date is missing, empty, or placeholder '---'
        is_active = df['offload_date'].isna() | (df['offload_date'] == '') | (df['offload_date'] == '---')
        active_rows = df[is_active]
        
        if 'truck_reg' in active_rows.columns:
            busy_trucks.update(active_rows['truck_reg'].dropna().astype(str).str.strip().tolist())
        if 'driver_name' in active_rows.columns:
            busy_drivers.update(active_rows['driver_name'].dropna().astype(str).str.strip().tolist())

    # Scan all 3 operations matrices
    extract_busy_units(engen_df)
    extract_busy_units(secondary_df)
    extract_busy_units(puma_df)

    # --- STEP 3: FILTER MASTER LISTS FOR DROPDOWNS ---
    # Only keep units that are NOT currently marked as busy
    available_trucks = [t for t in all_trucks if str(t).strip() not in busy_trucks]
    available_drivers = [d for d in all_drivers if str(d).strip() not in busy_drivers]

    # --- STEP 4: PREPARE DATA FOR HTML RENDER ---
    # Convert your puma trips data to dictionary objects for your frontend loop
    if not puma_df.empty:
        # Fill empty values with empty strings or placeholders so template doesn't crash
        puma_df = puma_df.fillna('---')
        current_puma_trips = puma_df.to_dict(orient='records')
    else:
        current_puma_trips = []

    # Dummy/Placeholder values for layout variables (Replace with your actual logic if needed)
    open_orders = [] 
    monthly_kpis = {}
    truck_map = {} 

    return render_template(
        'puma_trips.html',
        drivers=available_drivers,
        trucks=available_trucks,
        trips=current_puma_trips,
        open_orders=open_orders,
        monthly_kpis=monthly_kpis,
        truck_map=truck_map
    )

@app.route('/delete-puma-order/<order_number>')
def delete_puma_order(order_number):
    file_path = 'puma_trips.csv'
    
    if os.path.exists(file_path):
        try:
            # Load the current list
            df = pd.read_csv(file_path)
            
            # Keep everything EXCEPT the row matching the target puma_order_number
            # Cast column to string to match any text variations smoothly
            df['puma_order_number'] = df['puma_order_number'].astype(str).str.strip()
            clean_order_number = str(order_number).strip()
            
            # Filter row out
            filtered_df = df[df['puma_order_number'] != clean_order_number]
            
            # Save it back to storage
            filtered_df.to_csv(file_path, index=False)
            flash(f"Order {order_number} successfully removed.", "success")
            
        except Exception as e:
            flash(f"Error deleting order: {str(e)}", "danger")
    else:
        flash("Trips database file not found.", "danger")

    # Refresh the dashboard view
    return redirect(url_for('puma_trips_route'))

@app.route('/finance')
@login_required
def finance_dashboard():
    # 1. Load the data
    df = pd.read_csv('DATA/trips.csv')
    
    # Load rates and clean column names/data to ensure a perfect match
    try:
        df_rates = pd.read_csv('DATA/rates.csv')
        # Clean strings to prevent match failures due to hidden spaces or casing
        for col in ['customer', 'loading_point', 'offloading_point']:
            df_rates[col] = df_rates[col].astype(str).str.strip().str.upper()
            df[col + '_clean'] = df[col].astype(str).str.strip().str.upper()
    except Exception:
        # Fallback if rates.csv is missing or empty
        df_rates = pd.DataFrame(columns=['customer', 'loading_point', 'offloading_point', 'rate_per_litre'])

    # 2. Merge Trips with Rates
    # We join on Customer, Loading Point, and Offloading Point
    df = pd.merge(
        df, 
        df_rates, 
        left_on=['customer_clean', 'loading_point_clean', 'offloading_point_clean'],
        right_on=['customer', 'loading_point', 'offloading_point'],
        how='left',
        suffixes=('', '_r')
    )

    # 3. Setup numeric data and calculate amounts
    df['litres_offloaded'] = pd.to_numeric(df['litres_offloaded'], errors='coerce').fillna(0)
    # Use the rate from CSV; if no rate is found (NaN), default to 0.0
    df['rate_per_litre'] = df['rate_per_litre'].fillna(0.0)
    df['amount'] = df['litres_offloaded'] * df['rate_per_litre']
    
    # 4. Create the table data (OFFLOADED or INVOICED)
    trips_mask = df['status'].isin(['OFFLOADED', 'INVOICED'])
    trips_for_table = df[trips_mask].copy()
    
    # 5. Calculate Summary Cards (Only for 'OFFLOADED' trips)
    pending_df = df[df['status'] == 'OFFLOADED'].copy()
    total_val = pending_df['amount'].sum()
    
    summary_data = {}
    if not pending_df.empty:
        summary_data = pending_df.groupby('customer_x' if 'customer_x' in pending_df else 'customer').agg({
            'order_number': 'count',
            'amount': 'sum'
        }).to_dict(orient='index')

    # 6. Return to template
    return render_template('finance_dashboard.html', 
                           trips=trips_for_table.to_dict(orient='records'), 
                           summary=summary_data,
                           total_pending=total_val)


#=======================================WORKSHOP=================================================



@app.route('/workshop/add-inventory', methods=['POST'])
@login_required
def add_inventory():
    cost = float(request.form.get('cost_part', 0))
    
    new_item = {
        'category': request.form.get('category'),
        'part_number': request.form.get('part_number'),
        'opening_stock': int(request.form.get('opening_stock', 0)),
        'quantity_used': 0,
        'balance': int(request.form.get('opening_stock', 0)),
        'side': request.form.get('side'),
        'part_name': request.form.get('part_name'),
        'cost_part': cost,
        'inclusive': round(cost * 1.15, 2), # Auto-adds 15% VAT
        'truck_brand': request.form.get('truck_brand'),
        'shelf': request.form.get('shelf'),
        'store': request.form.get('store')
    }
    
    df = pd.read_csv('DATA/inventory.csv')
    df = pd.concat([df, pd.DataFrame([new_item])], ignore_index=True)
    df.to_csv('DATA/inventory.csv', index=False)
    
    return redirect(url_for('workshop_inventory'))

#================================================================================================

@app.route('/finance/generate/trip/<order_no>')
@login_required
def generate_single_invoice(order_no):
    # 1. Load the data
    df = pd.read_csv('DATA/trips.csv')
    
    # 2. Find the specific trip by Order Number
    # We ensure order_no is treated as a string to match CSV formatting
    mask = (df['order_number'].astype(str) == str(order_no)) & (df['status'] == 'OFFLOADED')
    
    if not df[mask].empty:
        # 3. Change status to INVOICED for this trip only
        df.loc[mask, 'status'] = 'INVOICED'
        
        # 4. Save back to CSV
        df.to_csv('DATA/trips.csv', index=False)
        flash(f"Invoice generated successfully for Order #{order_no}", "success")
    else:
        flash(f"Error: Trip #{order_no} not found or not ready for invoicing.", "danger")
        
    return redirect('/finance')


@app.route('/finance/process_invoice', methods=['POST'])
@login_required
def process_invoice():
    try:
        order_no = request.form.get('order_number')
        action = request.form.get('action') 
        
        # 1. Load Data
        df_trips = pd.read_csv('DATA/trips.csv')
        df_cust = pd.read_csv('DATA/customers.csv')
        df_rates = pd.read_csv('DATA/rates.csv')
        
        # 2. Get Trip Details
        trip_mask = df_trips['order_number'].astype(str) == str(order_no)
        if df_trips[trip_mask].empty:
            flash("Trip not found.", "danger")
            return redirect('/finance')
            
        trip = df_trips[trip_mask].iloc[0]
        
        # 3. AUTO-MATCH RATE (Cleaned and Robust)
        # Convert everything to string, strip spaces, and uppercase for a perfect match
        t_cust = str(trip['customer']).strip().upper()
        t_load = str(trip['loading_point']).strip().upper()
        t_offload = str(trip['offloading_point']).strip().upper()

        # Clean the rates dataframe for comparison
        df_rates['customer_clean'] = df_rates['customer'].str.strip().str.upper()
        df_rates['load_clean'] = df_rates['loading_point'].str.strip().str.upper()
        df_rates['offload_clean'] = df_rates['offloading_point'].str.strip().str.upper()

        rate_match = df_rates[
            (df_rates['customer_clean'] == t_cust) & 
            (df_rates['load_clean'] == t_load) & 
            (df_rates['offload_clean'] == t_offload)
        ]
        
        if not rate_match.empty:
            found_rate = float(rate_match.iloc[0]['rate_per_litre'])
        else:
            # If still not found, let's try to find a "Generic" customer rate
            found_rate = 0.0
            print(f"DEBUG: No rate found for {t_cust} from {t_load} to {t_offload}")
        
        # 4. Lookup Customer Info
        cust_match = df_cust[df_cust['customer_name'] == trip['customer']]
        address = cust_match.iloc[0]['address'] if not cust_match.empty else "No Address"
        vat_no = cust_match.iloc[0]['vat_no'] if not cust_match.empty else "N/A"

        # 5. Prepare PDF Payload
        inv_payload = {
            'inv_no': f"INV-{order_no}",
            'order_number': order_no,
            'customer': trip['customer'],
            'address': address,
            'vat_no': vat_no,
            # We combine points for the PDF description
            'route': f"{trip['loading_point']} to {trip['offloading_point']}",
            'litres': trip.get('litres_offloaded', 0),
            'rate': found_rate,
            'vat': 15,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'description': request.form.get('description', 'Fuel Transport')
        }

        # 6. Update CSV status to INVOICED
        df_trips.loc[trip_mask, 'status'] = 'INVOICED'
        df_trips.to_csv('DATA/trips.csv', index=False)

        # 7. Generate PDF
        from utils.invoice_generator import create_pdf
        pdf_path = create_pdf(inv_payload)

        if action == 'download':
            return send_file(pdf_path, as_attachment=True)
        return send_file(pdf_path) 

    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
        return redirect('/finance')
    
@app.route('/driver/profile/<bto_id>')
@login_required
def driver_profile(bto_id):
    df = pd.read_csv('DATA/bto_registry.csv')
    
    # Find the driver where bto_id matches
    # Note: We convert bto_id to string to ensure a match
    driver_data = df[df['bto_id'].astype(str) == str(bto_id)]
    
    if driver_data.empty:
        flash("Driver not found!", "danger")
        return redirect('/drivers')
    
    # Convert the single row to a dictionary
    driver = driver_data.to_dict(orient='records')[0]
    
    return render_template('driver_profile_card.html', d=driver)    

@app.route('/bto-manager')
@login_required
def bto_manager():
    df = get_bto_registry()
    stats = get_bto_stats(df)
    today = datetime.now()
    grouped_alerts = {}

    date_cols = [col for col in df.columns if 'Date' in col or 'Exp' in col or 'procedure' in col]

    for _, row in df.iterrows():
        driver_name = row['NAME/SURNAME']
        driver_docs = []

        # Inside your bto_manager loop in app.py:
        for col in date_cols:
            date_val = row.get(col, '')
            if date_val and date_val != '' and date_val != 'nan':
                try:
                    exp_date = datetime.strptime(str(date_val), '%Y-%m-%d')
                    days_left = (exp_date - today).days
                    
                    # REMOVE THE '0 <=' check. 
                    # This captures Karabo's 2025 date (which is roughly -64 days)
                    if days_left <= 60: 
                        if days_left < 0:
                            # Karabo's K53 will hit this branch
                            status_class = "expired-badge" 
                            days_text = f"EXPIRED ({abs(days_left)} days ago)"
                        else:
                            status_class = "urgent-badge" if days_left <= 30 else "upcoming-badge"
                            days_text = f"{days_left} Days left"

                        driver_docs.append({
                            'doc_name': col,
                            'expiry': date_val,
                            'days': days_left,
                            'days_text': days_text,
                            'class': status_class
                        })
                except:
                    continue
        
        if driver_docs:
            # SORTING LOGIC: Sort by 'days' key ascending (lowest days first)
            driver_docs.sort(key=lambda x: x['days'])
            grouped_alerts[driver_name] = driver_docs

    drivers_list = df.to_dict(orient='records')
    return render_template('drivers/bto_manager.html', 
                           drivers=drivers_list, 
                           stats=stats, 
                           alerts=grouped_alerts)

@app.route('/bto-save', methods=['POST'])

def bto_save():
    # 1. Load the existing registry as strings to prevent the int64 crash
    df = pd.read_csv('DATA/bto_registry.csv', dtype=str).fillna('')
    
    # 2. Get form data as a dictionary
    data = request.form.to_dict()
    bto_id = data.get('bto_id')
    is_edit = data.get('is_edit') == 'true'

    # Remove internal logic flags so they aren't saved to the CSV
    data.pop('is_edit', None)

    # 3. Handle EDIT or NEW entry
    if is_edit and bto_id:
        # Find the row index where bto_id matches
        idx_list = df.index[df['bto_id'].astype(str) == str(bto_id)].tolist()
        if idx_list:
            row_idx = idx_list[0]
            # Update only the columns that exist in the CSV
            for col in df.columns:
                if col in data:
                    df.at[row_idx, col] = str(data[col])
    else:
        # Create a new unique ID using a timestamp
        data['bto_id'] = datetime.now().strftime('%Y%m%d%H%M%S')
        
        # Create a new row dictionary, ensuring every CSV column has a value
        new_row = {col: str(data.get(col, '')) for col in df.columns}
        
        # Append to the dataframe
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

    # 4. Save back to CSV
    df.to_csv('DATA/bto_registry.csv', index=False)
    
    return redirect(url_for('bto_manager'))

@app.route('/bto-manager/delete/<bto_id>')
@login_required
def bto_delete(bto_id):
    from utils.drivers_module import delete_bto_entry
    delete_bto_entry(bto_id)
    return redirect(url_for('bto_manager'))

@app.route("/fatigue/hours", methods=["GET", "POST"])
def fatigue_hours():
    # --- 1. Fetch Drivers from bto_registry.csv ---
    drivers_list = []
    registry_path = "DATA/bto_registry.csv"

    if os.path.exists(registry_path):
        try:
            with open(registry_path, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Capture type DRIVER and manage potential legacy/empty type definitions
                    if row.get("TYPE") == "DRIVER" or not row.get("TYPE"):
                        name = row.get("NAME/SURNAME")
                        if name:
                            drivers_list.append({"NAME/SURNAME": name})
            # Prioritize clean display sequencing
            drivers_list = sorted(drivers_list, key=lambda x: x["NAME/SURNAME"])
        except Exception as e:
            print(f"Error reading registry payload context: {e}")

    # --- 2. Handle Form Submission ---
    if request.method == "POST":
        try:
            entry = {
                "date": request.form.get("date"),
                "driver_name": request.form.get("driver_name"),
                "customer": request.form.get("customer", "Other"),
                "start_time": request.form.get("start_time"),
                "end_time": request.form.get("end_time"),
                "off_day": request.form.get("off_day", "no"),
                "after_hours_reason": request.form.get("after_hours_reason", ""),
            }
            add_working_hour(entry)
            flash("✅ Working hours logged successfully!", "success")
            return redirect(url_for("fatigue_hours"))
        except Exception as e:
            flash(f"❌ Error saving record to sheet storage: {str(e)}", "danger")

    # --- 3. Process Fatigue Records & Aggregations ---
    records = load_working_hours()
    for i, r in enumerate(records):
        r["index"] = i  # Maps target actions for inline updates/deletes securely

    enriched = enrich_records(records)
    structure = group_by_year_month_driver(enriched)

    # Calculate deep analytical mappings for drivers and dynamic table indices
    monthly_summary = summarize_by_driver_month(enriched)
    weekly_summary = summarize_by_driver_week(enriched)
    rotation = get_roster_status()

    # --- THE CRITICAL METRIC ENGINE FIX ---
    # Running both logic passes to satisfy the top layout layer and the nested loop blocks
    global_totals = calculate_global_customer_totals(enriched)
    monthly_customer_totals = calculate_monthly_customer_totals(enriched)

    # --- 4. Defaults & Current UI Presentation Context ---
    today = date.today()
    current_year = today.year
    current_month = today.strftime("%B")
    current_date = today.strftime("%Y-%m-%d")

    return render_template(
        "fatigue/hours.html",
        drivers=drivers_list,
        structure=structure,
        monthly_summary=monthly_summary,
        weekly_summary=weekly_summary,
        rotation=rotation,
        global_totals=global_totals,                 # Resolves Jinja2 UndefinedError for the top block cards
        monthly_customer_totals=monthly_customer_totals,  # Populates the inside tab panel KPIs
        current_year=current_year,                   # Drives JS onload focus parameters
        current_month=current_month,                 # Drives JS onload focus parameters
        current_date=current_date,                   # Provides fallback tracking to datepickers
        default_year=current_year,
        default_month=current_month,
    )


@app.route("/fatigue/hours/delete/<int:index>", methods=["POST"])
def delete_fatigue_entry(index):
    delete_working_hour(index)
    flash("✅ Entry deleted successfully.", "success")
    return redirect(url_for("fatigue_hours"))


@app.route("/fatigue/update", methods=["POST"])
@login_required
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

CSV_PATH = os.path.join('DATA', 'roster.csv')

@app.route('/fatigue/roster')
@login_required
def index():
    drivers, meta = process_advanced_roster_data()
    return render_template('fatigue/roster.html', drivers=drivers, meta=meta)


# Import or include your name normalizer helper to keep matching watertight
def normalize_driver_name(name):
    if pd.isnull(name):
        return ""
    return str(name).strip().lower().replace("'", "").replace("`", "").replace(" ", "")

@app.route('/fatigue/update-driver', methods=['POST'])
def update_driver():
    # 1. Gather incoming form inputs
    posted_name = request.form.get('driver_name', '').strip()
    date_truck_taken = request.form.get('date_truck_taken', '').strip()
    date_off_taken = request.form.get('date_off_taken', '').strip()
    
    if not posted_name:
        flash("Error: Missing driver target name.", "danger")
        return redirect(url_for('roster_page')) # Change to your actual roster view route function name

    # 2. Establish paths to data tables
    roster_csv = os.path.join('DATA', 'roster.csv')
    registry_csv = os.path.join('DATA', 'bto_registry.csv')
    
    # 3. Read files securely
    df_registry = pd.read_csv(registry_csv).fillna('') if os.path.exists(registry_csv) else pd.DataFrame()
    df_roster = pd.read_csv(roster_csv).fillna('') if os.path.exists(roster_csv) else pd.DataFrame()

    # 4. Resolve the exact registry match to maintain structural integrity
    registry_name_col = 'NAME/SURNAME' if 'NAME/SURNAME' in df_registry.columns else 'driver_name'
    
    if df_registry.empty or registry_name_col not in df_registry.columns:
        flash("System Error: Master driver registry missing headers.", "danger")
        return redirect(url_for('roster_page'))

    # Match the incoming name using fuzzy logic against master registry records
    target_registry_name = None
    normalized_posted = normalize_driver_name(posted_name)
    
    for _, row in df_registry.iterrows():
        reg_name = str(row[registry_name_col]).strip()
        if normalize_driver_name(reg_name) == normalized_posted:
            target_registry_name = reg_name
            break

    # Fallback to the posted string if not found explicitly in master records
    if not target_registry_name:
        target_registry_name = posted_name

    # 5. Build or read the current active state map
    # Ensure columns exist if roster.csv is freshly initialized
    if df_roster.empty or 'driver' not in df_roster.columns:
        df_roster = pd.DataFrame(columns=['driver', 'date_truck_taken', 'date_off_taken'])
    
    # Standardize string lookups on the dataframe index
    df_roster['driver'] = df_roster['driver'].str.strip()
    df_roster.set_index('driver', inplace=True, drop=False)

    # 6. Apply state changes mutually exclusively (Duty vs. Rest)
    # If the user input a "Truck Taken" date, they are entering work duty, which terminates their home rest time
    if date_truck_taken:
        new_truck_val = date_truck_taken
        new_off_val = "" # Clear off-duty records to allow work calculations to trigger
    elif date_off_taken:
        new_truck_val = "" # Clear truck duty records to transition status into resting state
        new_off_val = date_off_taken
    else:
        flash("No date value submitted. Changes dropped.", "warning")
        return redirect(url_for('index'))

    # Write modifications directly to data rows
    df_roster.loc[target_registry_name, 'driver'] = target_registry_name
    df_roster.loc[target_registry_name, 'date_truck_taken'] = new_truck_val
    df_roster.loc[target_registry_name, 'date_off_taken'] = new_off_val

    # 7. Persist records back to the local drive storage
    try:
        # Reset index layout prior to outputting file array values
        df_roster.reset_index(drop=True, inplace=True)
        df_roster.to_csv(roster_csv, index=False)
        flash(f"Roster registry update saved for {target_registry_name} successfully.", "success")
    except Exception as e:
        flash(f"Disk Write Error: Unable to preserve modifications. Details: {str(e)}", "danger")

    return redirect(url_for('index'))

# --- COMPLIANCE MODULE ROUTES ---

# Document Rules
DOCUMENT_RULES = {
    'TRUCK': [
        'License disc', 'Engen Dekra SLP', 'Vopak Dekra SLP', 
        'Fire Permit', 'Brake Test', 'Trem Card', 'Cross Border'
    ],
    'TRAILER': [
        'License disc', 'Engen Dekra SLP', 'Vopak Dekra SLP', 
        'Fire Permit', 'Brake Test', 'Pressure Test', 
        'Meter Calibration Certificate', 'Trem Card'
    ]
}

@app.route('/add-compliance', methods=['POST'])
def add_compliance():
    unit_id = request.form.get('unit_id').upper()
    category = request.form.get('category') # We'll add this to the form
    doc_name = request.form.get('name')
    expiry_date = request.form.get('expiry_date')

    # Validation: Check if the doc is allowed for this category
    if doc_name not in DOCUMENT_RULES.get(category, []):
        # You could return an error message here
        return f"Error: {doc_name} is not allowed for {category}", 400

    csv_path = 'DATA/compliance.csv'
    fieldnames = ['id', 'unit_id', 'category', 'name', 'expiry_date', 'reminder']
    
    new_row = {
        'id': str(uuid.uuid4())[:8],
        'unit_id': unit_id,
        'category': category,
        'name': doc_name,
        'expiry_date': expiry_date,
        'reminder': ''
    }

    with open(csv_path, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writerow(new_row)
        
    return redirect(url_for('compliance_dashboard'))

@app.route('/compliance-module')
@login_required
def compliance_dashboard():
    """
    Renders the main compliance dashboard with 10 truck/trailer pairs
    and the 3 summary cards (Expired, 30-day, 60-day).
    """
    try:
        # get_compliance_data() returns (fleet_list, summary_dict)
        fleet, summary = get_compliance_data()
        return render_template('vehicles/compliance.html', fleet=fleet, summary=summary)
    except FileNotFoundError:
        return "Error: DATA/compliance.csv not found. Please ensure the file exists."

@app.route('/update-compliance-date', methods=['POST'])
def update_compliance_date():
    """
    Handles the modal submission. It reads the CSV, updates the 
    specific document ID, and writes it back to the file.
    """
    doc_id = request.form.get('doc_id')
    new_date = request.form.get('new_date')
    csv_path = 'DATA/compliance.csv'
    
    updated_rows = []
    fieldnames = []

    # 1. Read current data
    if os.path.exists(csv_path):
        with open(csv_path, mode='r', newline='') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            for row in reader:
                # Update the date only for the matching ID
                if row['id'] == doc_id:
                    row['expiry_date'] = new_date
                updated_rows.append(row)

        # 2. Write back to CSV
        with open(csv_path, mode='w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(updated_rows)

    # Redirect back to the compliance dashboard specifically
    return redirect(url_for('compliance_dashboard'))


@app.route('/delete-compliance', methods=['POST'])
def delete_compliance():
    doc_id = request.form.get('doc_id')
    csv_path = 'DATA/compliance.csv'
    
    rows = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            if row['id'] != doc_id:
                rows.append(row)
                
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        
    return redirect(url_for('compliance_dashboard'))




# --- Helper function to filter the CSV ---
# Change the order to: path, units, days, id_col
def get_filtered_data(csv_path, selected_units, days_limit, id_col='unit_id'):
    if not os.path.exists(csv_path):
        return pd.DataFrame()

    df = pd.read_csv(csv_path)
    
    # Filter by IDs
    if selected_units:
        df = df[df[id_col].isin(selected_units)]
    
    # Filter by Date
    if days_limit and days_limit != "":
        df['expiry_date'] = pd.to_datetime(df['expiry_date'])
        limit_date = datetime.now() + timedelta(days=int(days_limit))
        df = df[df['expiry_date'] <= limit_date]
        df['expiry_date'] = df['expiry_date'].dt.strftime('%Y-%m-%d')
    
    return df

@app.route('/report-excel/<source>', methods=['POST'])
@login_required
def report_excel(source):
    # Determine the file and ID column based on the source
    if source == 'compliance':
        csv_path = 'DATA/compliance.csv'
        id_col = 'unit_id'
        ids = request.form.getlist('units')
        days = request.form.get('days')
    else: # source == 'vehicles'
        csv_path = 'DATA/vehicles.csv'
        id_col = 'truck_reg'
        ids = request.form.getlist('trucks')
        days = None
    
    # Use your existing helper
    df = get_filtered_data(csv_path, ids, days, id_col=id_col)
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 
                     as_attachment=True, download_name=f"{source}_Report.xlsx")

@app.route('/report-pdf/<source>', methods=['POST'])
@login_required
def report_pdf(source):
    from reportlab.pdfgen import canvas
    
    # Determine settings based on source
    if source == 'compliance':
        csv_path = 'DATA/compliance.csv'
        id_col = 'unit_id'
        ids = request.form.getlist('units')
        days = request.form.get('days')
    else:
        csv_path = 'DATA/vehicles.csv'
        id_col = 'truck_reg'
        ids = request.form.getlist('trucks')
        days = None

    df = get_filtered_data(csv_path, ids, days, id_col=id_col)

    buffer = BytesIO()
    p = canvas.Canvas(buffer)
    # ... (Keep your existing PDF drawing logic here)
    p.save()
    buffer.seek(0)
    return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name=f"{source}_Report.pdf")

# --- END COMPLIANCE MODULE ---

@app.route("/vehicles/services/<truck_reg>", methods=["GET", "POST"])
@login_required
def vehicle_service_history(truck_reg):
    if request.method == "POST":
        # 1. Add the record to the Service History file
        add_service_entry(request.form)
        
        # 2. Update the Vehicle Master List (Next Service KM)
        new_service_km = request.form.get("service_km")
        next_goal_km = request.form.get("next_service_km")
        
        vehicles = load_vehicles()
        updated = False
        for v in vehicles:
            if v.get("truck_reg") == truck_reg:
                # Update the target and reset current km to the service reading
                v["last_service_km"] = new_service_km
                v["current_km"] = new_service_km 
                v["next_service_km"] = next_goal_km
                v["last_km_update"] = datetime.today().strftime("%Y-%m-%d")
                updated = True
                break
        
        if updated:
            save_vehicles(vehicles)
            
        flash(f"✅ Service for {truck_reg} logged. Next service at {next_goal_km} km.", "success")
        return redirect(url_for("vehicle_service_history", truck_reg=truck_reg))

    # GET Method logic
    all_services = load_services()
    truck_services = [s for s in all_services if s.get("truck_reg") == truck_reg]

    return render_template(
        "vehicles/service_history.html",
        truck_reg=truck_reg,
        services=truck_services
    )


@app.route("/fuel")
@login_required
def fuel_page():
    from utils.fuel_logic import analyze_fuel_intelligence, load_unassigned_trips
    
    # 1. Run the Analysis to get stats and pre-calculated logs
    # Note: stats['drivers'] is now guaranteed to exist
    analysis, all_logs = analyze_fuel_intelligence()
    
    # 2. Load unassigned trips for the dropdowns
    unassigned, trips_list = load_unassigned_trips()
    
    # 3. Create fast lookup for template logic
    trips_fast_lookup = {str(t.get('order_number')): t for t in trips_list}

    # 4. Reverse logs for "newest first" display
    display_logs = all_logs.copy()
    display_logs.reverse()
    
    # Show last 150 for page performance
    #display_logs = display_logs[:150]

    return render_template(
        "fuel.html", 
        fuel_logs=display_logs, 
        analysis=analysis, 
        unassigned_trips=unassigned, 
        trips_fast_lookup=trips_fast_lookup,
        trips_json=json.dumps(trips_list)
    )

@app.route("/fuel/add", methods=["POST"])
def fuel_add():
    from utils.fuel_logic import add_fuel_entry, load_fuel
    order_no = request.form.get("order_number")
    force = request.form.get("force_add") == "true"
    
    # Efficient Duplicate Check
    if order_no and order_no != "CUSTOM" and not force:
        logs = load_fuel()
        if any(str(l.get('order_number')) == str(order_no) for l in logs):
            return jsonify({"success": False, "is_duplicate": True})

    add_fuel_entry(request.form)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({"success": True})
    
    return redirect("/fuel")

@app.route("/fuel/edit", methods=["POST"])
def edit_fuel():
    from utils.fuel_logic import load_fuel, save_fuel
    logs = load_fuel()
    target_id = request.form.get("id")
    
    for log in logs:
        if str(log.get('id')) == str(target_id):
            # Clean numeric data to prevent math errors later
            log.update({
                'order_number': request.form.get("order_number"),
                'date': request.form.get("date"),
                'truck_reg': request.form.get("truck_reg"),
                'driver': request.form.get("driver"),
                'litres': float(request.form.get("litres") or 0),
                'km_at_fuel': int(request.form.get("km_at_fuel") or 0),
                'cost': float(request.form.get("cost") or 0)
            })
            break
            
    save_fuel(logs)
    return redirect("/fuel")

@app.route("/fuel/delete/<id>")
def delete_fuel(id):
    from utils.fuel_logic import load_fuel, save_fuel
    logs = load_fuel()
    # Filter out the deleted ID
    new_logs = [l for l in logs if str(l.get('id')) != str(id)]
    save_fuel(new_logs)
    return redirect("/fuel")


@app.route("/trips/skip-fuel", methods=["POST"])
@login_required
def skip_fuel():
    data = request.json
    order_no = data.get('order_number')
    reason = data.get('reason')

    # Load your trips.csv
    import pandas as pd
    df = pd.read_csv("DATA/trips.csv")
    
    # Add a skip reason to the specific trip
    if 'fuel_skip_reason' not in df.columns:
        df['fuel_skip_reason'] = ""
    
    df.loc[df['order_number'].astype(str) == str(order_no), 'fuel_skip_reason'] = reason
    df.to_csv("DATA/trips.csv", index=False)

    return jsonify({"success": True})

@app.route("/vehicles/fuel-facs", methods=['GET', 'POST'])
@login_required
def fuel_facs_page():
    tankers_path = 'DATA/tankers.csv'
    vehicles_path = 'DATA/vehicles.csv'

    # --- HANDLE SAVING SPECS (POST) ---
    if request.method == 'POST':
        reg = request.form.get('trailer_reg', '').strip()
        prod = request.form.get('primary_product', 'ADO').upper()
        
        if not reg:
            flash("❌ Error: Trailer Registration cannot be blank.", "danger")
            return redirect(url_for('fuel_facs_page'))

        try:
            cpts = [int(request.form.get(f'cpt_{i}', 0) or 0) for i in range(1, 10)]
            total_cap = sum(cpts)
            
            all_cols = [
                'trailer_reg', 'total_capacity', 'primary_product',
                'cpt_1', 'cpt_2', 'cpt_3', 'cpt_4', 'cpt_5', 'cpt_6', 'cpt_7', 'cpt_8', 'cpt_9',
                'total_ado', 'cpt_1_ado', 'cpt_2_ado', 'cpt_3_ado', 'cpt_4_ado', 'cpt_5_ado', 'cpt_6_ado', 'cpt_7_ado', 'cpt_8_ado', 'cpt_9_ado',
                'total_ulp', 'cpt_1_ulp', 'cpt_2_ulp', 'cpt_3_ulp', 'cpt_4_ulp', 'cpt_5_ulp', 'cpt_6_ulp', 'cpt_7_ulp', 'cpt_8_ulp', 'cpt_9_ulp',
                'total_ik', 'cpt_1_ik', 'cpt_2_ik', 'cpt_3_ik', 'cpt_4_ik', 'cpt_5_ik', 'cpt_6_ik', 'cpt_7_ik', 'cpt_8_ik', 'cpt_9_ik'
            ]

            if os.path.exists(tankers_path):
                df_specs = pd.read_csv(tankers_path, dtype=str)
                df_specs.columns = [c.strip() for c in df_specs.columns]
                
                for col in all_cols:
                    if col not in df_specs.columns:
                        df_specs[col] = '0'
            else:
                df_specs = pd.DataFrame(columns=all_cols)

            if prod == 'ADO':
                target_suffix = '_ado'
                summary_target = 'total_ado'
            elif prod == 'ULP':
                target_suffix = '_ulp'
                summary_target = 'total_ulp'
            elif prod == 'IK':
                target_suffix = '_ik'
                summary_target = 'total_ik'
            else:
                target_suffix = '_ado'
                summary_target = 'total_ado'

            df_specs['trailer_reg'] = df_specs['trailer_reg'].fillna('').astype(str).str.strip()
            match_mask = df_specs['trailer_reg'].str.lower() == str(reg).lower()

            if match_mask.any():
                idx = df_specs[match_mask].index[0]
                df_specs.at[idx, 'trailer_reg'] = reg
                df_specs.at[idx, 'primary_product'] = prod
                df_specs.at[idx, 'total_capacity'] = str(total_cap)
                
                for i in range(1, 10):
                    df_specs.at[idx, f'cpt_{i}'] = str(cpts[i-1])
                
                df_specs.at[idx, summary_target] = str(total_cap)
                for i in range(1, 10):
                    df_specs.at[idx, f'cpt_{i}{target_suffix}'] = str(cpts[i-1])
            else:
                new_record = {col: '0' for col in all_cols}
                new_record['trailer_reg'] = reg
                new_record['primary_product'] = prod
                new_record['total_capacity'] = str(total_cap)
                
                for i in range(1, 10):
                    new_record[f'cpt_{i}'] = str(cpts[i-1])
                
                new_record[summary_target] = str(total_cap)
                for i in range(1, 10):
                    new_record[f'cpt_{i}{target_suffix}'] = str(cpts[i-1])

                df_specs = pd.concat([df_specs, pd.DataFrame([new_record])], ignore_index=True)

            df_specs = df_specs[all_cols]
            df_specs.to_csv(tankers_path, index=False)
            flash(f"✅ Technical Card for {reg} updated successfully.", "success")
        except Exception as e:
            print(f"Error saving technical card: {e}")
            flash(f"❌ Error saving configuration data: {str(e)}", "danger")
            
        return redirect(url_for('fuel_facs_page'))

    # --- HANDLE DISPLAY (GET) ---
    try:
        df_vehicles = pd.read_csv(vehicles_path, dtype=str)
        df_vehicles.columns = [c.strip() for c in df_vehicles.columns]
        
        if 'trailer_reg' in df_vehicles.columns:
            df_vehicles['trailer_reg'] = df_vehicles['trailer_reg'].fillna('').astype(str).str.strip()
            master_trailers = df_vehicles[df_vehicles['trailer_reg'] != ''].copy()
            master_trailers = master_trailers[['trailer_reg']].drop_duplicates()
        else:
            master_trailers = pd.DataFrame(columns=['trailer_reg'])

        if os.path.exists(tankers_path):
            df_specs = pd.read_csv(tankers_path, dtype=str)
            df_specs.columns = [c.strip() for c in df_specs.columns]
            df_specs['trailer_reg'] = df_specs['trailer_reg'].fillna('').astype(str).str.strip()
            df_specs = df_specs[df_specs['trailer_reg'] != '']
        else:
            df_specs = pd.DataFrame(columns=['trailer_reg', 'total_capacity', 'primary_product'])

        df_combined = pd.merge(master_trailers, df_specs, on='trailer_reg', how='left')
        
        fill_values = {
            'total_capacity': '0', 
            'primary_product': 'Unassigned',
            'total_ado': '0', 'total_ulp': '0', 'total_ik': '0'
        }
        for i in range(1, 10):
            fill_values[f'cpt_{i}'] = '0'
            fill_values[f'cpt_{i}_ado'] = '0'
            fill_values[f'cpt_{i}_ulp'] = '0'
            fill_values[f'cpt_{i}_ik'] = '0'
            
        df_combined = df_combined.fillna(fill_values)

        for col in fill_values.keys():
            if col not in df_combined.columns:
                df_combined[col] = fill_values[col]

        total_fleet = int(pd.to_numeric(df_combined['total_capacity'], errors='coerce').fillna(0).sum())
        ado_cap = int(pd.to_numeric(df_combined['total_ado'], errors='coerce').fillna(0).sum())
        ulp_cap = int(pd.to_numeric(df_combined['total_ulp'], errors='coerce').fillna(0).sum())
        
        fleet_stats = {
            "total": total_fleet,
            "ulp": ulp_cap,
            "ado": ado_cap,
            "count": len(df_combined)
        }
        
        trailers = []
        for _, row in df_combined.iterrows():
            clean_row = {str(k).strip(): str(v).strip() for k, v in row.to_dict().items()}
            js_safe_dict = clean_row.copy()
            
            clean_row['trailer_reg'] = clean_row.get('trailer_reg', '').strip()
            clean_row['primary_product'] = clean_row.get('primary_product', 'Unassigned').strip()
            clean_row['to_dict'] = js_safe_dict
            trailers.append(clean_row)
        
    except Exception as e:
        print(f"Critical error in fuel-facs route: {e}")
        trailers = []
        fleet_stats = {"total": 0, "ulp": 0, "ado": 0, "count": 0}

    return render_template("vehicles/fuel-facs.html", trailers=trailers, fleet_stats=fleet_stats)


@app.route('/vehicles/add-client', methods=['POST'])
@login_required
def add_client():

    client = request.form.get('client_name','').strip()

    if not client:
        flash("Client name required","danger")
        return redirect(url_for('fuel_facs_page'))

    tankers_path = 'DATA/tankers.csv'
    vehicles_path = 'DATA/vehicles.csv'

    df_vehicles = pd.read_csv(vehicles_path,dtype=str)

    if os.path.exists(tankers_path):
        df_specs = pd.read_csv(tankers_path,dtype=str)
    else:
        df_specs = pd.DataFrame()

    rows = []

    trailers = (
        df_vehicles['trailer_reg']
        .fillna('')
        .astype(str)
        .str.strip()
        .unique()
    )

    for trailer in trailers:

        if not trailer:
            continue

        exists = (
            (df_specs['trailer_reg'].astype(str).str.lower()==trailer.lower()) &
            (df_specs['client'].astype(str).str.lower()==client.lower())
        ).any()

        if exists:
            continue

        rows.append({
            'trailer_reg': trailer,
            'client': client,
            'total_capacity': '0',
            'primary_product': 'ADO'
        })

    if rows:
        df_specs = pd.concat(
            [df_specs,pd.DataFrame(rows)],
            ignore_index=True
        )

    df_specs.to_csv(tankers_path,index=False)

    flash(f'{client} client created','success')

    return redirect(
        url_for('fuel_facs_page',client=client)
    )


@app.route("/vehicles")
@login_required
def vehicle_list():
    vehicles = load_vehicles()
    trips = load_trips()

    # Build active truck set from trips
    active_trucks = {t["truck_reg"] for t in trips if t.get("status") in ["IN TRANSIT","LOADING"]}

    enriched = []
    service_due = 0
    service_overdue = 0
    km_missing = 0
    assigned = 0
    unassigned = 0
    km_updated = 0

    for v in vehicles:
        status, km_to_service = calculate_service_status(v)
        km_warning = km_update_required(v)

        if status == "OVERDUE":
            service_overdue += 1
        elif status == "DUE":
            service_due += 1

        if km_warning:
            km_missing += 1
        else:
            km_updated += 1

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
        "km_updated": km_updated,
        "assigned": assigned,
        "unassigned": unassigned,
        "active_trucks": len(active_trucks),
        "idle_trucks": len(vehicles) - len(active_trucks)
    }

    return render_template("vehicles.html", vehicles=enriched, summary=summary, now_date=date.today().strftime('%Y-%m-%d'))

@app.route('/vehicles/generate_custom_report', methods=['POST'])
@login_required
def generate_custom_report():
    # 1. Get the date from the form
    report_date = request.form.get('report_date')
    
    # 2. Get current vehicle data (Assuming you have a get_vehicles() function)
    # If your data is in vehicles.csv, reload it here
    df = pd.read_csv('DATA/vehicles.csv')
    
    # 3. Create the simplified report DataFrame
    report_df = df[['truck_reg', 'current_km', 'next_service_km', 'km_to_service']].copy()
    report_df.columns = ['truck_reg', 'current_km', 'next_service', 'km_left_to_service']
    
    # 4. Save to a temporary file
    filename = f"KM_Report_{report_date}.csv"
    report_df.to_csv(filename, index=False)
    
    # 5. Send the file to the browser
    return send_file(filename, as_attachment=True)

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



# --- HELPERS ---
def get_data(file):
    if not os.path.exists(file): return []
    with open(file, mode='r', encoding='utf-8') as f:
        return list(csv.DictReader(f))

def save_data(file, data, fields):
    with open(file, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(data)



from flask import Flask, render_template, request, redirect, url_for, send_file
from fpdf import FPDF

# Define the path to your data
BREAKDOWN_FILE = 'breakdowns.csv'

def read_csv(file_path):
    if not os.path.exists(file_path):
        return []
    with open(file_path, mode='r', encoding='utf-8') as f:
        return list(csv.DictReader(f))

def write_csv(file_path, data):
    # Fieldnames must match all possible columns in your breakdown system
    fieldnames = [
    'breakdown_id', 
    'truck_reg', 
    'driver', 
    'location', 
    'issue_description', 
    'reported_date', 
    'reported_time', 
    'km_at_breakdown', 
    'status', 
    'repair_start_date', 
    'repair_end_date', 
    'downtime_hours', 
    'repair_cost', 
    'workshop', 
    'notes',
    # New fields for Job Card
    'mechanic',
    'work_done',
    'parts_issued',
    'start_date',
    'end_date'
]
    with open(file_path, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)

# Updated field list including all new fields for the Job Card/Modal
BREAKDOWN_FIELDS = [
    'breakdown_id', 
    'truck_reg', 
    'driver', 
    'location', 
    'issue_description', 
    'reported_date', 
    'reported_time', 
    'km_at_breakdown', 
    'status', 
    'repair_start_date', 
    'repair_end_date', 
    'downtime_hours', 
    'repair_cost', 
    'workshop', 
    'notes',
    # New fields for Job Card
    'mechanic',
    'work_done',
    'parts_issued',
    'start_date',
    'end_date'
]

# --- ROUTES ---

@app.route('/workshop')
@login_required
def workshop():
    # --- 1. HANDLE JOBS (Your existing logic) ---
    breakdowns_list = read_csv('DATA/breakdowns.csv')
    active_jobs = []
    for b in breakdowns_list:
        # Check status and convert to jobcard format
        if b.get('status') in ['SEEN', 'IN REPAIR', 'REPORTED']:
            # This helper function handles the key mapping (TRUCK REG, etc.)
            job = convert_breakdown_to_jobcard(b.get('breakdown_id'), breakdowns_list)
            if job:
                active_jobs.append(job)

    # --- 2. HANDLE INVENTORY (The missing part) ---
    csv_path = 'DATA/inventory.csv'
    inventory = []
    
    if os.path.exists(csv_path) and os.stat(csv_path).st_size > 0:
        df = pd.read_csv(csv_path)
        # Clean and calculate as you did before
        df['opening_stock'] = pd.to_numeric(df['opening_stock'], errors='coerce').fillna(0)
        df['quantity_used'] = pd.to_numeric(df['quantity_used'], errors='coerce').fillna(0)
        df['cost_part'] = pd.to_numeric(df['cost_part'], errors='coerce').fillna(0.0)
        
        df['balance'] = df['opening_stock'] - df['quantity_used']
        df['inclusive'] = (df['cost_part'] * 1.15).round(2)
        
        # Sort so highest stock is first
        df = df.sort_values(by='opening_stock', ascending=False)
        inventory = df.to_dict(orient='records')

    # --- 3. RETURN BOTH ---
    return render_template('workshop.html', 
                           jobs=active_jobs, 
                           inventory=inventory)

@app.route('/breakdowns')
def breakdowns_list():
    breakdowns = get_data('DATA/breakdowns.csv')
    vehicles = get_data('DATA/vehicles.csv')
    drivers = get_data('DATA/bto_registry.csv')
    return render_template('breakdowns/breakdowns.html', breakdowns=breakdowns, vehicles=vehicles, drivers=drivers)

@app.route('/breakdowns', methods=['POST'])
def add_breakdown():
    data = get_data('DATA/breakdowns.csv')
    new_entry = {k: request.form.get(k, '') for k in BREAKDOWN_FIELDS}
    new_entry['breakdown_id'] = datetime.now().strftime("%y%m%d%H%M%S")
    new_entry['status'] = 'REPORTED'
    data.append(new_entry)
    save_data('DATA/breakdowns.csv', data, BREAKDOWN_FIELDS)
    return redirect(url_for('breakdowns_list'))

@app.route('/breakdowns/close/<id>', methods=['POST'])
def close_breakdown(id):
    # 1. Load your data
    data = get_data('DATA/breakdowns.csv')
    
    # 2. Extract data from the modal form
    mechanic = request.form.get('MECHENIC\'S NAME')
    end_date = request.form.get('DATE CLOSED')
    work_done = request.form.get('WORK DONE')
    odo = request.form.get('ODO READING')
    part_name = request.form.get('PART NAME')
    part_code = request.form.get('PART NUMBER/CODE')
    cost_part = request.form.get('COST/PART')
    consumeables = request.form.get('CONSUMEABLES')
    labour = request.form.get('LABOUR')
    
    # Simple validation
    if not mechanic or not end_date:
        return "Error: Mechanic and Date Closed are required.", 400

    # 3. Update the specific row
    for b in data:
        if str(b.get('breakdown_id')) == str(id):
            b['mechanic'] = mechanic
            b['end_date'] = end_date
            b['work_done'] = work_done
            b['km_at_breakdown'] = odo  # Updating Odo if changed
            b['parts_issued'] = f"{part_name} ({part_code})"
            # Calculate total cost or save components
            b['repair_cost'] = float(cost_part or 0) + float(consumeables or 0) + float(labour or 0)
            b['status'] = 'REPAIRED'
    
    # 4. Save the updated CSV
    save_data('DATA/breakdowns.csv', data, BREAKDOWN_FIELDS)
    
    # Flash the success message
    flash('Job Completed Successfully!', 'success')

    # 5. Redirect to generate the PDF automatically
    return redirect(url_for('workshop'))

@app.route('/breakdowns/delete/<id>')
def delete_breakdown(id):
    data = [b for b in get_data('breakdowns.csv') if b['id'] != id]
    save_data('breakdowns.csv', data, BREAKDOWN_FIELDS)
    return redirect(url_for('breakdowns_list'))

# --- PDF GENERATION (Matching COMO JOB CARD) ---

@app.route('/breakdowns/to_workshop/<id>')
def to_workshop(id):
    rows = read_csv('DATA/breakdowns.csv')
    for row in rows:
        if str(row['breakdown_id']) == str(id):
            row['status'] = 'IN REPAIR'
            
    write_csv('DATA/breakdowns.csv', rows)
    return redirect(url_for('workshop'))

@app.route('/workshop/seen/<id>')
def mark_seen(id):
    data = get_data('DATA/breakdowns.csv')
    for b in data:
        if str(b.get('breakdown_id')) == str(id):
            b['status'] = 'SEEN'
    write_csv('DATA/breakdowns.csv', data)
    return redirect(url_for('workshop'))

@app.route('/workshop/to_repair/<id>')
def to_repair(id):
    data = get_data('DATA/breakdowns.csv')
    for b in data:
        if str(b.get('breakdown_id')) == str(id):
            b['status'] = 'IN REPAIR'
    save_data('DATA/breakdowns.csv', data, BREAKDOWN_FIELDS)
    flash('Job moved to IN REPAIR.', 'warning')
    return redirect(url_for('workshop'))
@app.route('/breakdowns/pdf/<id>')
def generate_pdf(id):
    breakdowns = get_data('DATA/breakdowns.csv')
    b = next((item for item in breakdowns if str(item.get('breakdown_id')) == str(id)), None)
    
    if not b:
        return "Record not found", 404

    pdf = FPDF()
    pdf.add_page()
    
    # --- HEADER ---
    pdf.set_font("Arial", 'B', 20)
    pdf.cell(0, 10, "HIPPO TRANSPORT", ln=True, align='C')
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 5, "Ficksburg, Free State", ln=True, align='C')
    pdf.ln(10)
    pdf.line(10, 30, 200, 30) # Horizontal line
    
    # --- TITLE & JOB ID ---
    pdf.set_fill_color(230, 230, 230)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "JOB CARD", ln=True, align='C', fill=True)
    pdf.ln(5)
    
    # --- INFO TABLE (Organized in two columns) ---
    pdf.set_font("Arial", 'B', 10)
    pdf.set_fill_color(245, 245, 245)
    
    # Row 1
    pdf.cell(45, 8, " J.C. Number:", border=1, fill=True)
    pdf.set_font("Arial", '', 10)
    pdf.cell(50, 8, b.get('breakdown_id', 'N/A'), border=1)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(45, 8, " Date Reported:", border=1, fill=True)
    pdf.set_font("Arial", '', 10)
    pdf.cell(50, 8, b.get('reported_date', 'N/A'), border=1, ln=True)
    
    # Row 2
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(45, 8, " Registration:", border=1, fill=True)
    pdf.set_font("Arial", '', 10)
    pdf.cell(50, 8, b.get('truck_reg', 'N/A'), border=1)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(45, 8, " Odo Reading:", border=1, fill=True)
    pdf.set_font("Arial", '', 10)
    pdf.cell(50, 8, b.get('km_at_breakdown', 'N/A'), border=1, ln=True)

    # Row 3
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(45, 8, " Mechanic:", border=1, fill=True)
    pdf.set_font("Arial", '', 10)
    pdf.cell(145, 8, b.get('mechanic', 'N/A'), border=1, ln=True)

    pdf.ln(10)

    # --- JOB DESCRIPTION ---
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 8, " WORK DETAILS", ln=True, fill=True)
    pdf.set_font("Arial", '', 10)
    issue = b.get('issue_description', 'N/A')
    work = b.get('work_done', 'N/A')
    pdf.multi_cell(0, 8, f"REPORTED ISSUE:\n{issue}\n\nWORK PERFORMED:\n{work}", border=1)
    
    pdf.ln(5)

    # --- FINANCIALS ---
    try:
        total = float(b.get('repair_cost', 0))
    except:
        total = 0.0
    
    subtotal = total / 1.15
    tax = total - subtotal
    
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(140, 8, "SUBTOTAL (Excl. VAT)", border=1, align='R')
    pdf.cell(50, 8, f"R {subtotal:,.2f}", border=1, ln=True, align='R')
    pdf.cell(140, 8, "VAT (15%)", border=1, align='R')
    pdf.cell(50, 8, f"R {tax:,.2f}", border=1, ln=True, align='R')
    pdf.set_fill_color(200, 200, 200)
    pdf.cell(140, 10, "TOTAL AMOUNT", border=1, align='R', fill=True)
    pdf.cell(50, 10, f"R {total:,.2f}", border=1, ln=True, align='R', fill=True)

    # --- FOOTER / SIGNATURES ---
    pdf.ln(20)
    pdf.set_font("Arial", '', 10)
    pdf.cell(95, 10, "Driver Signature: ______________________", border=0)
    pdf.cell(95, 10, "Workshop Manager: ______________________", border=0, ln=True)

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
    pdf.output(temp_file.name)
    temp_file.close()

    return send_file(temp_file.name, as_attachment=True, download_name=f"JobCard_{id}.pdf")

# -------------------- TRIPS ROUTES --------------------


def calculate_toll_fee(truck_reg):
    """
    SA Trucks (FS) = R800
    Lesotho Trucks (C...BBW/BBM/etc) = R440
    """
    reg = str(truck_reg).strip().upper()
    if reg.endswith('FS'):
        return 800
    else:
        return 440


def get_toll_data(trip_row):
    # 1. Determine Fee based on Truck Registration
    # SA Trucks end in 'FS', Lesotho Trucks usually end in 'B...'
    reg = str(trip_row['truck_reg']).strip().upper()
    fee = 800 if reg.endswith('FS') else 440

    # 2. Lookup Driver Payment Number from your records
    # Loading your driver contact list (ensure you have this CSV)
    try:
        drivers_df = pd.read_csv('DATA/bto_registry.csv')
        driver_info = drivers_df[drivers_df['name'] == trip_row['NAME/SURNAME']]
        
        if not driver_info.empty:
            mpesa = driver_info.iloc[0].get('phone_number')
            ecocash = driver_info.iloc[0].get('ecocash_number')
            
            # Waterfall: M-Pesa first, then EcoCash
            if pd.notna(mpesa) and str(mpesa).strip():
                payment_no = f"{mpesa} (M-Pesa)"
            elif pd.notna(ecocash) and str(ecocash).strip():
                payment_no = f"{ecocash} (EcoCash)"
            else:
                payment_no = "No Number"
        else:
            payment_no = "Driver Not Found"
    except FileNotFoundError:
        payment_no = "Check drivers.csv"

    return fee, payment_no

@app.route('/mark-toll-paid', methods=['POST'])
def mark_toll_paid():
    order_no = request.form.get('order_no')
    trips_path = 'DATA/puma_trips.csv'
    
    if os.path.exists(trips_path):
        df = pd.read_csv(trips_path)
        
        # If 'toll_paid' column doesn't exist yet, create it
        if 'toll_paid' not in df.columns:
            df['toll_paid'] = 'N'
            
        # Update the specific order
        df.loc[df['puma_order_number'] == order_no, 'toll_paid'] = 'Y'
        
        # Save back to CSV
        df.to_csv(trips_path, index=False)
        
    return redirect(url_for('toll_management'))

def get_payment_number(driver_name):
    # Load your drivers CSV
    drivers_df = pd.read_csv('DATA/bto_registry.csv')
    driver = drivers_df[drivers_df['name'] == 'NAME/SURNAME']
    
    if not driver.empty:
        # Check M-Pesa first
        mpesa = driver.iloc[0].get('phone_number')
        # Check EcoCash (Econet) second
        ecocash = driver.iloc[0].get('ecocash_number')
        
        if pd.notna(mpesa) and str(mpesa).strip():
            return f"{mpesa} (M-Pesa)"
        elif pd.notna(ecocash) and str(ecocash).strip():
            return f"{ecocash} (EcoCash)"
            
    return "No Number"


@app.route('/toll-management')
def toll_management():
    import pandas as pd
    import os

    registry_path = 'DATA/bto_registry.csv'
    trips_path = 'DATA/puma_trips.csv'
    
    if not os.path.exists(registry_path) or not os.path.exists(trips_path):
        return "Missing CSV files in DATA folder."

    # Load and clean headers
    reg_df = pd.read_csv(registry_path)
    reg_df.columns = reg_df.columns.str.strip()
    
    trips_df = pd.read_csv(trips_path)
    trips_df.columns = trips_df.columns.str.strip()

    # Get the country from the dropdown (defaults to Lesotho)
    selected_country = request.args.get('country', 'Lesotho')

    # Filter by Destination Country (Lesotho or South Africa)
    if 'destination_country' in trips_df.columns:
        mask = trips_df['destination_country'].str.strip().str.upper() == selected_country.upper()
        toll_trips = trips_df[mask].copy()
    else:
        return f"Error: Column 'destination_country' not found. Available: {list(trips_df.columns)}"

    processed_list = []
    for _, row in toll_trips.iterrows():
        # Mapping to your actual column names from the error message:
        driver_name = str(row.get('driver_name', '')).strip()
        truck_reg = str(row.get('truck_reg', '')).strip().upper()
        
        # Fee logic: SA registration (FS) gets 800, others get 440
        fee = 800 if truck_reg.endswith('FS') else 440

        # Lookup in Registry using 'NAME/SURNAME'
        driver_match = reg_df[reg_df['NAME/SURNAME'].str.strip() == driver_name]
        
        payment_no = "No Number"
        if not driver_match.empty:
            voda = driver_match.iloc[0].get('phone_number')
            eco = driver_match.iloc[0].get('econet_number')
            
            if pd.notna(voda) and str(voda).strip():
                payment_no = f"{str(int(float(voda)))} (M-Pesa)"
            elif pd.notna(eco) and str(eco).strip():
                payment_no = f"{str(int(float(eco)))} (EcoCash)"

        processed_list.append({
            'date': row.get('loading_date'), # Using your 'loading_date' column
            'driver': driver_name,
            'reg': truck_reg,
            'order': row.get('puma_order_number'), # Using your order column
            'site': row.get('discharge_point'), # This is the equivalent of Offloading Site
            'payment_no': payment_no,
            'amount': fee,
            'paid': row.get('invoiced') == 'Y' # Using invoiced as a proxy for paid status
        })

    total_sum = sum(item['amount'] for item in processed_list)

    return render_template('toll_management.html', 
                           trips=processed_list, 
                           total_sum=total_sum,
                           selected_country=selected_country)

@app.route("/check_km_logic", methods=["POST"])
def check_km_logic():
    data = request.json
    truck_reg = data.get('truck_reg', '').strip().upper()
    # We check Loading KM for Rule A/B
    entered_km = int(data.get('loading_km', 0)) 
    
    v_df = pd.read_csv("DATA/vehicles.csv")
    truck_row = v_df[v_df['truck_reg'].str.upper() == truck_reg]
    
    if not truck_row.empty:
        last_km = int(truck_row.iloc[0]['current_km'])
        
        # Rule A: Hard Block
        if entered_km < last_km:
            return jsonify({
                "status": "block", 
                "msg": f"❌ Impossible! {truck_reg} is already at {last_km:,} KM. You cannot save a lower Loading KM."
            })
        
        # Rule B: 2000km Warning
        if (entered_km - last_km) > 2000:
            return jsonify({
                "status": "warn", 
                "msg": f"The last known reading for {truck_reg} was {last_km:,} KM. You are entering {entered_km:,} KM. Are you sure?"
            })
                
    return jsonify({"status": "ok"})

@app.route('/trips/upload', methods=['GET', 'POST'])
@login_required
def upload_orders():
    if request.method == 'POST':
        # Check if file was provided in the post request
        if 'file' not in request.files:
            flash('No file part in the request')
            return redirect(request.url)
        
        file = request.files['file']
        
        if file.filename == '':
            flash('No file selected for upload')
            return redirect(request.url)

        if file and file.filename.endswith('.csv'):
            filepath = 'DATA/orders.csv'
            
            # 1. Read the newly uploaded CSV
            # dtype=str is vital to keep order numbers exactly as they appear
            try:
                new_df = pd.read_csv(file, dtype=str).fillna('')
            except Exception as e:
                flash(f"Error reading file: {e}")
                return redirect(request.url)

            # 2. Check for the existing pool file
            if os.path.exists(filepath):
                existing_df = pd.read_csv(filepath, dtype=str).fillna('')
                # Merge the two lists
                combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            else:
                combined_df = new_df

            # 3. Remove Duplicates based on the 'order_number' column
            initial_count = len(combined_df)
            combined_df.drop_duplicates(subset=['order_number'], keep='first', inplace=True)
            final_count = len(combined_df)
            
            # Calculate how many were actually new
            new_added = final_count - (len(existing_df) if os.path.exists(filepath) else 0)
            duplicates_removed = initial_count - final_count

            # 4. Write back to the DATA folder
            combined_df.to_csv(filepath, index=False)
            
            flash(f"Success! Added {new_added} new orders. ({duplicates_removed} duplicates were skipped).")
            return redirect(url_for('upload_orders'))

    # Points to your specific template location
    return render_template('trips/upload.html')

@app.route("/trips", methods=["GET", "POST"])
@login_required
def trips():
    # 1. PATH SETUP
    ORDERS_PATH = "DATA/orders.csv"
    TRIPS_PATH = "DATA/trips.csv"
    VEHICLES_PATH = "DATA/vehicles.csv"
    DRIVERS_PATH = "DATA/bto_registry.csv"

    # 2. HANDLE NEW TRIP SUBMISSION
    if request.method == "POST":
        # Create a mutable copy of the form data
        trip_data = request.form.to_dict()
        
        # Capture the action, then remove it from the data so it isn't saved to CSV
        action = trip_data.pop('action', 'save') 
        order_number = trip_data.get('order_number')
        
        # Now pass the clean trip_data (without 'action') to your function
        success = add_trip(trip_data)
        
        if not success:
            flash("❌ Order number already exists!", "error")
            return redirect(url_for("trips"))
        
        # If "Save & Print" was clicked, go straight to PDF generation
        if action == 'save_and_print':
            flash("✅ Trip saved! Generating Loading Advice...", "success")
            return redirect(url_for("generate_loading_advice", order_no=order_number))
        
        flash("✅ Trip added successfully!", "success")
        return redirect(url_for("trips"))
    
    mtd_litres = 0
    trips_mtd = 0
    km_mtd = 0
    fuel_mtd = 0
    work_hours_mtd = 0

    # 4. LOAD AND PROCESS TRIPS FOR MTD STATS
    all_trips = load_trips()
    df_trips = pd.DataFrame(all_trips)

    # 3. INITIALIZE MTD VARIABLES & TIME
    now = datetime.now()
    curr_year = str(now.year)      # "2026"
    curr_month = now.strftime('%m') # "04"
    
    busy_trucks = set()
    busy_drivers = set()

    if not df_trips.empty:
        # Clean up status for logic checks
        df_trips['status_clean'] = df_trips['status'].fillna('').astype(str).str.upper().str.strip()
        
        # A: Filter Busy Resources (Resources currently under a load)
        busy_df = df_trips[~df_trips['status_clean'].isin(['OFFLOADED', 'INVOICED'])]
        busy_trucks = set(busy_df['truck_reg'].astype(str).str.strip().str.upper())
        busy_drivers = set(busy_df['driver'].astype(str).str.strip().str.title())

        # B: MTD CALCULATION (Excel-Proof String Matching)
        # We look at 'date_offloaded' for delivered stats
        if 'date_offloaded' in df_trips.columns:
            df_trips['date_str'] = df_trips['date_offloaded'].fillna('').astype(str)
            
            # This mask catches "04" and "2026" anywhere in the string (handles / or -)
            mtd_mask = df_trips['date_str'].str.contains(curr_year) & \
                       df_trips['date_str'].str.contains(curr_month)
            
            mtd_df = df_trips[mtd_mask].copy()

            if not mtd_df.empty:
                # Calculate Litres (strip spaces/commas first)
                if 'litres_offloaded' in mtd_df.columns:
                    l_clean = mtd_df['litres_offloaded'].astype(str).str.replace(r'[ ,]', '', regex=True)
                    mtd_litres = pd.to_numeric(l_clean, errors='coerce').fillna(0).sum()
                
                # Count only completed/invoiced trips for the MTD card
                trips_mtd = len(mtd_df[mtd_df['status_clean'].isin(['OFFLOADED', 'INVOICED'])])

                # Calculate KM Travelled
                if 'km_travelled' in mtd_df.columns:
                    km_clean = mtd_df['km_travelled'].astype(str).str.replace(r'[ ,]', '', regex=True)
                    km_mtd = pd.to_numeric(km_clean, errors='coerce').fillna(0).sum()

    # 5. LOAD OTHER MTD DATA (Fuel & Hours)
    try:
        fuel_data = load_fuel()
        for f in fuel_data:
            f_date = str(f.get('date', ''))
            if curr_year in f_date and f_date.count(curr_month) > 0:
                fuel_mtd += float(f.get('litres', 0) or 0)
    except: pass

    try:
        # Assuming you have an existing function to get hours
        records = load_working_hours()
        enriched = enrich_records(records)
        for r in enriched:
            r_date = str(r.get('date', ''))
            if curr_year in r_date and curr_month in r_date:
                work_hours_mtd += float(r.get('hours_worked', 0))
    except: pass

    # 6. FILTER DROPDOWNS (Hide busy Trucks/Drivers)
    available_orders = []
    if os.path.exists(ORDERS_PATH):
        orders_df = pd.read_csv(ORDERS_PATH, dtype={'order_number': str})
        if not df_trips.empty:
            used_orders = df_trips['order_number'].astype(str).unique()
            orders_df = orders_df[~orders_df['order_number'].astype(str).isin(used_orders)]
        available_orders = orders_df.to_dict('records')

    vehicles_list = []
    if os.path.exists(VEHICLES_PATH):
        v_df = pd.read_csv(VEHICLES_PATH)
        v_df = v_df[~v_df['truck_reg'].astype(str).str.upper().isin(busy_trucks)]
        vehicles_list = v_df.to_dict('records')

    drivers_list = []
    if os.path.exists(DRIVERS_PATH):
        d_df = pd.read_csv(DRIVERS_PATH)
        d_df = d_df[~d_df['NAME/SURNAME'].astype(str).str.title().isin(busy_drivers)]
        drivers_list = d_df.to_dict('records')

    # 7. FINALIZE FOR TEMPLATE
    auto_update_all_vehicle_km()
    trips_by_month = group_trips_by_month(all_trips)
    
    stats = {
        'fuel_mtd': fuel_mtd,
        'trips_mtd': trips_mtd,
        'km_mtd': km_mtd,
        'work_hours_mtd': round(work_hours_mtd, 1),
        'revenue_mtd': 0 # Calculate this similar to litres if rates are available
    }
    
    return render_template(
        "trips/trips.html",
        trips_by_month=trips_by_month,
        current_month=now.strftime("%B"),
        available_orders=available_orders,
        vehicles=vehicles_list,
        drivers=drivers_list,
        stats=stats,
        mtd_litres=mtd_litres,
        all_months=list(trips_by_month.keys())
    )

#----------------------------EMPTINESS------------------------------------------------------------


@app.route('/generate-emptiness-cert/<order_no>')
@login_required
def generate_emptiness_cert(order_no):
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = os.path.join(PROJECT_ROOT, 'DATA')

    try:
        # Load Data
        puma_df = pd.read_csv(os.path.join(DATA_DIR, 'puma_trips.csv'), dtype=str)
        engen_df = pd.read_csv(os.path.join(DATA_DIR, 'trips.csv'), dtype=str)
        
        # Standardize headers
        puma_df.columns = [str(c).strip().lower() for c in puma_df.columns]
        engen_df.columns = [str(c).strip().lower() for c in engen_df.columns]

        # 1. Identify Trip Record
        trip = None
        source = None
        if order_no in puma_df['puma_order_number'].values:
            trip = puma_df[puma_df['puma_order_number'] == order_no].iloc[0]
            source = 'PUMA'
        elif order_no in engen_df['order_number'].values:
            trip = engen_df[engen_df['order_number'] == order_no].iloc[0]
            source = 'ENGEN'
        else:
            flash(f"Order {order_no} not found.", "danger")
            return redirect(url_for('trips'))

        # 2. Extract Data
        trailer_reg = str(trip.get('trailer_reg', '')).strip()
        
       # 3. Dynamic Compartment Logic
        tankers_df = pd.read_csv(os.path.join(DATA_DIR, 'tankers.csv'))
        
        # Clean trailer_reg to ensure they match
        tankers_df['trailer_reg'] = tankers_df['trailer_reg'].astype(str).str.strip()
        trailer_reg_clean = str(trailer_reg).strip()
        
        compartments = []
        v_info = tankers_df[tankers_df['trailer_reg'] == trailer_reg_clean]
        
        if not v_info.empty:
            # We look for cpt_1 through cpt_9
            for i in range(1, 10):
                col_name = f'cpt_{i}'
                # Check if column exists and if it has a value > 0
                if col_name in v_info.columns:
                    val = v_info.iloc[0][col_name]
                    # Ensure it is a number and greater than 0
                    try:
                        if float(val) > 0:
                            compartments.append({'number': i})
                    except (ValueError, TypeError):
                        continue
        
        # 4. Context for Template
        context = {
            'order_no': order_no,
            'date': datetime.now().strftime('%d/%m/%Y'),
            'driver': trip.get('driver' if source == 'ENGEN' else 'driver_name', 'N/A'),
            'truck': trip.get('truck_reg', 'N/A'),
            'trailer': trailer_reg,
            # Change your logo_path line to this:
            'logo_path': 'file:///' + os.path.join(PROJECT_ROOT, 'static', 'images', 'logo.png').replace('\\', '/'),
            'compartments': compartments
        }

        # 5. Generate PDF
        html_content = render_template('emptiness_cert.html', **context)
        
        path_to_wkhtmltopdf = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'
        config = pdfkit.configuration(wkhtmltopdf=path_to_wkhtmltopdf)
        
        # Use the exact same 'bulletproof' options from the working route
        options = {
            'page-size': 'A4',
            'margin-top': '0',
            'margin-bottom': '0',
            'margin-left': '0',
            'margin-right': '0',
            'enable-local-file-access': None, # Note: None is preferred over True in some versions
            'quiet': '',
            'disable-smart-shrinking': '',
            'no-stop-slow-scripts': '',
            'load-error-handling': 'ignore',
            'load-media-error-handling': 'ignore'
        }
        
        pdf = pdfkit.from_string(
            html_content, 
            False, 
            configuration=config, 
            options=options # <--- YOU MUST PASS THIS
        )
        
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename=Emptiness_Cert_{order_no}.pdf'
        return response

    except Exception as e:
        flash(f"Error generating certificate: {str(e)}", "danger")
        return redirect(url_for('trips'))

#++++++++++++SECONDARY TRIPS+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
CSV_PATH = 'DATA/secondary_trips.csv'
VEHICLES_PATH = 'DATA/vehicles.csv'
REGISTRY_PATH = 'DATA/bto_registry.csv'

def safe_int(val, default=0):
    """Safely extracts integers preventing internal server formatting type errors."""
    try:
        if val is None or str(val).strip() == "":
            return default
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return default

def safe_float(val, default=0.0):
    """Safely extracts floats preventing internal server formatting type errors."""
    try:
        if val is None or str(val).strip() == "":
            return default
        return float(str(val).strip())
    except (ValueError, TypeError):
        return default

def initialize_secondary_csv():
    if not os.path.exists('DATA'):
        os.makedirs('DATA')
    if not os.path.exists(CSV_PATH):
        df = pd.DataFrame(columns=[
            'trip_id', 'date_loaded', 'order_number', 'customer', 'product', 
            'truck_reg', 'trailer_reg', 'driver', 'status', 'loading_point', 
            'litres_loaded', 'loading_km', 'position', 'offloading_point', 
            'offloading_km', 'date_offloaded', 'litres_offloaded', 'dn_number', 
            'difference_litres', 'difference_km', 'km_travelled', 'trip_type'
        ])
        df.to_csv(CSV_PATH, index=False)

@app.route('/trips/secondary_trips')
def secondary_trips():
    initialize_secondary_csv()
    
    # Utilizing your pre-existing asset files without duplicating values
    try:
        df_v = pd.read_csv(VEHICLES_PATH)
        if 'truck_reg' in df_v.columns:
            df_v = df_v.drop_duplicates(subset=['truck_reg'])
        vehicles = df_v.to_dict('records')
    except Exception:
        vehicles = []

    try:
        df_r = pd.read_csv(REGISTRY_PATH)
        if 'NAME/SURNAME' in df_r.columns:
            df_r = df_r.drop_duplicates(subset=['NAME/SURNAME'])
        drivers = df_r.to_dict('records')
    except Exception:
        drivers = []

    trips = []
    try:
        df_t = pd.read_csv(CSV_PATH)
        if not df_t.empty:
            df_t['litres_loaded'] = pd.to_numeric(df_t['litres_loaded'], errors='coerce').fillna(0).astype(int)
            df_t['litres_offloaded'] = pd.to_numeric(df_t['litres_offloaded'], errors='coerce').fillna(0).astype(int)
            trips = df_t.to_dict('records')
    except Exception:
        trips = []
    auto_update_all_vehicle_km()
    return render_template(
        'secondary_trips.html', 
        trips=trips, 
        vehicles=vehicles, 
        drivers=drivers
    )

@app.route('/api/save_multi_drop_trip', methods=['POST'])
def save_multi_drop_trip():
    initialize_secondary_csv()
    data = request.json or {}
    header = data.get('header', {})
    stops = data.get('stops', [])

    if not stops:
        return jsonify({"status": "error", "message": "At least one stop manifest component must be provided."}), 400

    generated_trip_id = f"{str(header.get('truck_reg')).replace(' ', '')}_{int(time.time())}"
    
    try:
        df = pd.read_csv(CSV_PATH)
    except Exception:
        df = pd.DataFrame()

    new_rows = []
    for stop in stops:
        l_load = safe_int(stop.get('litres_loaded'))
        l_off = safe_int(stop.get('litres_offloaded'))
        diff_litres = l_off - l_load
        
        s_km = safe_float(header.get('loading_km'))
        e_km = safe_float(header.get('offloading_km'))
        diff_km = e_km - s_km if e_km > 0 else 0.0

        row = {
            'trip_id': generated_trip_id,
            'date_loaded': header.get('date_loaded'),
            'order_number': stop.get('order_number'),
            'customer': stop.get('offloading_point'),
            'product': stop.get('product'),
            'truck_reg': header.get('truck_reg'),
            'trailer_reg': header.get('trailer_reg'),
            'driver': header.get('driver'),
            'status': stop.get('status', 'IN TRANSIT'),
            'loading_point': header.get('loading_point', 'WALTLOO'),
            'litres_loaded': l_load,
            'loading_km': s_km,
            'position': stop.get('offloading_point'),
            'offloading_point': stop.get('offloading_point'),
            'offloading_km': e_km,
            'date_offloaded': header.get('date_loaded') if stop.get('status') == 'DELIVERED' else '',
            'litres_offloaded': l_off,
            'dn_number': stop.get('dn_number'),
            'difference_litres': diff_litres,
            'difference_km': diff_km,
            'km_travelled': diff_km,
            'trip_type': 'LOCAL_MULTI_DROP'
        }
        new_rows.append(row)

    df_new = pd.DataFrame(new_rows)
    df_combined = pd.concat([df, df_new], ignore_index=True)
    
    try:
        df_combined.to_csv(CSV_PATH, index=False)
    except PermissionError:
        return jsonify({"status": "error", "message": "Permission Denied: Ensure DATA/secondary_trips.csv is not open in Excel."}), 500
    
    return jsonify({"status": "success", "message": "Multi-drop voyage dispatched successfully."})

@app.route('/api/get_multi_drop_trip/<trip_id>', methods=['GET'])
def get_multi_drop_trip(trip_id):
    if not os.path.exists(CSV_PATH):
        return jsonify({"status": "error", "message": "Database file not found."}), 404

    df = pd.read_csv(CSV_PATH)
    df_filtered = df[df['trip_id'] == trip_id]

    if df_filtered.empty:
        return jsonify({"status": "error", "message": "Requested collection execution context not found."}), 404

    first_row = df_filtered.iloc[0]
    header_data = {
        "trip_id": str(first_row.get('trip_id')),
        "date_loaded": str(first_row.get('date_loaded')),
        "truck_reg": str(first_row.get('truck_reg')),
        "trailer_reg": str(first_row.get('trailer_reg') if pd.notna(first_row.get('trailer_reg')) else ""),
        "driver": str(first_row.get('driver')),
        "loading_point": str(first_row.get('loading_point')),
        "loading_km": safe_float(first_row.get('loading_km')),
        "offloading_km": safe_float(first_row.get('offloading_km')) if pd.notna(first_row.get('offloading_km')) and str(first_row.get('offloading_km')).strip() != "" else ""
    }

    stops_list = []
    for _, row in df_filtered.iterrows():
        stops_list.append({
            "order_number": str(row.get('order_number') if pd.notna(row.get('order_number')) else ""),
            "offloading_point": str(row.get('offloading_point') if pd.notna(row.get('offloading_point')) else ""),
            "product": str(row.get('product')),
            "litres_loaded": safe_int(row.get('litres_loaded')),
            "litres_offloaded": safe_int(row.get('litres_offloaded')),
            "dn_number": str(row.get('dn_number') if pd.notna(row.get('dn_number')) else ""),
            "status": str(row.get('status', 'IN TRANSIT'))
        })
    auto_update_all_vehicle_km()
    return jsonify({"header": header_data, "stops": stops_list})

@app.route('/api/update_multi_drop_trip', methods=['POST'])
def update_multi_drop_trip():
    data = request.json or {}
    header = data.get('header', {})
    stops = data.get('stops', [])
    trip_id = header.get('trip_id')

    if not trip_id or not os.path.exists(CSV_PATH):
        return jsonify({"status": "error", "message": "Missing structural tracking references."}), 400

    try:
        df = pd.read_csv(CSV_PATH)
        if 'trip_id' in df.columns:
            df = df[df['trip_id'] != trip_id]
    except Exception:
        df = pd.DataFrame()

    updated_rows = []
    for stop in stops:
        l_load = safe_int(stop.get('litres_loaded'))
        l_off = safe_int(stop.get('litres_offloaded'))
        diff_litres = l_off - l_load
        
        s_km = safe_float(header.get('loading_km'))
        e_km = safe_float(header.get('offloading_km'))
        diff_km = e_km - s_km if e_km > 0 else 0.0

        row = {
            'trip_id': trip_id,
            'date_loaded': header.get('date_loaded'),
            'order_number': stop.get('order_number'),
            'customer': stop.get('offloading_point'),
            'product': stop.get('product'),
            'truck_reg': header.get('truck_reg'),
            'trailer_reg': header.get('trailer_reg'),
            'driver': header.get('driver'),
            'status': stop.get('status', 'IN TRANSIT'),
            'loading_point': header.get('loading_point'),
            'litres_loaded': l_load,
            'loading_km': s_km,
            'position': stop.get('offloading_point'),
            'offloading_point': stop.get('offloading_point'),
            'offloading_km': e_km,
            'date_offloaded': header.get('date_loaded') if stop.get('status') == 'DELIVERED' else '',
            'litres_offloaded': l_off,
            'dn_number': stop.get('dn_number'),
            'difference_litres': diff_litres,
            'difference_km': diff_km,
            'km_travelled': diff_km,
            'trip_type': 'LOCAL_MULTI_DROP'
        }
        updated_rows.append(row)

    df_updated = pd.DataFrame(updated_rows)
    df_final = pd.concat([df, df_updated], ignore_index=True)
    
    try:
        df_final.to_csv(CSV_PATH, index=False)
    except PermissionError:
        return jsonify({"status": "error", "message": "Permission Denied: Close your CSV file if open in Excel."}), 500
    auto_update_all_vehicle_km()
    return jsonify({"status": "success", "message": "Trip log parameters synchronized successfully."})

@app.route('/api/delete_multi_drop_trip/<trip_id>', methods=['DELETE'])
def delete_multi_drop_trip(trip_id):
    if not os.path.exists(CSV_PATH):
        return jsonify({"status": "error", "message": "Target database not found."}), 404

    try:
        df = pd.read_csv(CSV_PATH)
        if 'trip_id' in df.columns:
            df = df[df['trip_id'] != trip_id]
        df.to_csv(CSV_PATH, index=False)
    except PermissionError:
        return jsonify({"status": "error", "message": "File Locked: Could not purge registry index rows."}), 500

    return jsonify({"status": "success", "message": "Target journey elements removed."})

@app.route("/trips/upload", methods=["GET", "POST"])
def upload_trips():
    if request.method == "POST":
        file = request.files["file"]
        if file and file.filename.endswith('.csv'):
            new_orders = pd.read_csv(file)
            
            # Path to your pool
            orders_path = "DATA/orders.csv"
            
            if os.path.exists(orders_path):
                # Load existing pool and append new ones
                existing_orders = pd.read_csv(orders_path)
                combined = pd.concat([existing_orders, new_orders])
                # Remove duplicates based on order_number
                combined.drop_duplicates(subset=['order_number'], keep='last', inplace=True)
                combined.to_csv(orders_path, index=False)
            else:
                new_orders.to_csv(orders_path, index=False)
                
            flash("Order pool updated successfully!", "success")
            return redirect(url_for("upload_trips")) 
            
    return render_template("trips/upload.html")



# 2. Update your route to call the new helper name
@app.route("/trips/delete/<order_number>", methods=["POST"])
@login_required
def delete_trip_route(order_number):
    perform_trip_deletion(order_number)
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
    
    return redirect(url_for("trips"))


# --- HELPER: Load Drivers from bto-registry.csv ---
def get_registry_drivers():
    drivers = []
    if os.path.exists('DATA/bto_registry.csv'):
        with open('DATA/bto_registry.csv', mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('TYPE') == 'DRIVER' or not row.get('TYPE'):
                    drivers.append({'NAME/SURNAME': row.get('NAME/SURNAME', 'Unknown')})
    return sorted(drivers, key=lambda x: x['NAME/SURNAME'])

# --- HELPER: Load Trucks from vehicles.csv ---
def get_vehicles():
    vehicles = []
    if os.path.exists('DATA/vehicles.csv'):
        with open('DATA/vehicles.csv', mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                vehicles.append({'Registration': row.get('Registration')})
    return vehicles

# --- TYRE DATA PERSISTENCE ---


def load_tyres():
    if not os.path.exists('tyres.csv'): return []
    with open('tyres.csv', mode='r', encoding='utf-8') as f:
        return list(csv.DictReader(f))

def save_tyres(tyres):
    fields = ["serial_no", "size", "brand", "purchase_date", "cost", "supplier", "status", 
              "truck_reg", "position", "km_fitted", "driver_name", "installer", 
              "km_removed", "removal_reason", "disposition", "total_km"]
    with open('tyres.csv', mode='w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(tyres)

# --- ROUTES ---

@app.route("/tyres/buy", methods=["POST"])
def buy_tyre():
    # 1. Get data from the modal form
    serial_no = request.form.get("serial_no")
    
    # 2. Prevent empty or duplicate serial numbers
    if not serial_no:
        flash("❌ Serial number is required!", "danger")
        return redirect("/tyres")

    new_tyre = {
        "serial_no": serial_no,
        "size": request.form.get("size"),
        "brand": request.form.get("brand"),
        "purchase_date": request.form.get("purchase_date"),
        "cost": request.form.get("cost", "0"),
        "supplier": request.form.get("supplier"),
        "status": "Stock",  # Default status when bought
        "truck_reg": "", 
        "position": "", 
        "km_fitted": "", 
        "driver_name": "", 
        "installer": "", 
        "km_removed": "",
        "removal_reason": "", 
        "disposition": "", 
        "total_km": "0"
    }

    # 3. Load existing, append new, and save
    tyres = load_tyres()
    
    # Check if serial already exists to prevent duplication
    if any(t['serial_no'] == serial_no for t in tyres):
        flash(f"❌ Tyre with serial {serial_no} already exists!", "danger")
        return redirect("/tyres")

    tyres.append(new_tyre)
    save_tyres(tyres)
    
    flash(f"✅ Tyre {serial_no} added to stock successfully!", "success")
    return redirect("/tyres")

@app.route("/tyres")
def tyre_inventory():
    tyres = load_tyres()
    return render_template("tyres.html", 
        tyres=tyres,
        drivers=get_registry_drivers(),
        vehicles=get_vehicles(),
        current_date=datetime.now().strftime('%Y-%m-%d'),
        stock_count=len([t for t in tyres if t['status'] == 'Stock']),
        fitted_count=len([t for t in tyres if t['status'] == 'Fitted']),
        retread_count=len([t for t in tyres if t['status'] == 'Retread']),
        scrap_count=len([t for t in tyres if t['status'] == 'Scrap'])
    )

@app.route("/tyres/fit", methods=["POST"])
def fit_tyre():
    serial = request.form.get("serial_no")
    tyres = load_tyres()
    for t in tyres:
        if t['serial_no'] == serial:
            t.update({
                "status": "Fitted",
                "truck_reg": request.form.get("truck_reg"),
                "position": request.form.get("position"),
                "km_fitted": request.form.get("km_fitted"),
                "driver_name": request.form.get("driver_name"),
                "installer": request.form.get("installer")
            })
    save_tyres(tyres)
    flash(f"Tyre {serial} fitted successfully.", "success")
    return redirect("/tyres")

@app.route("/tyres/remove", methods=["POST"])
def remove_tyre():
    serial = request.form.get("serial_no")
    km_out = int(request.form.get("km_removed") or 0)
    tyres = load_tyres()
    for t in tyres:
        if t['serial_no'] == serial:
            km_in = int(t['km_fitted'] or 0)
            t.update({
                "status": request.form.get("disposition"),
                "km_removed": km_out,
                "total_km": km_out - km_in,
                "removal_reason": request.form.get("reason"),
                "disposition": request.form.get("disposition"),
                "truck_reg": "", "position": "" # Clear vehicle association
            })
    save_tyres(tyres)
    return redirect("/tyres")

# -------------------- COMPLIANCE & DASHBOARD --------------------


@app.route("/vehicles/list")
@login_required
def vehicles_list():
    list_data = load_list()
    return render_template("vehicles/list.html", list=list_data)



# -------------------- DRIVERS --------------------

@app.route("/drivers/drivers")
@login_required
def drivers():
    drivers = load_drivers()
    return render_template("drivers/drivers.html", drivers=drivers)


@app.route("/drivers/contacts")
@login_required
def driver_contacts():
    return render_template("drivers/contacts.html")


@app.route("/drivers/violations")
@login_required
def driver_violations():
    return render_template("drivers/violations.html")


@app.route("/drivers/training")
@login_required
def driver_training():
    return render_template("drivers/training.html")

from collections import OrderedDict
@app.route('/drivers/loads')
@login_required
def driver_loads():
    # Base directory path setup where your CSVs live (adjust as needed)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Combined storage structure
    loads_data = {}

    # -------------------------------------------------------------------------
    # DATA WRANGLING HELPER FOR REUSABLE PARSING
    # -------------------------------------------------------------------------
    def process_trip_records(df_records, source_type):
        for _, row in df_records.iterrows():
            # --- 1. Normalize Column Mappings per File Structure ---
            if source_type == 'ENGEN':
                raw_driver = str(row.get('driver', 'Unknown Driver')).strip()
                date_val = row.get('date_loaded')
                order_num = row.get('order_number', 'N/A')
                load_pnt = row.get('loading_point', 'N/A')
                off_pnt = row.get('offloading_point', 'N/A')
                truck = row.get('truck_reg', 'N/A')
                # Secondary features initialized to empty defaults for fallback parity
                product_val = ''
                trip_id_key = None
            elif source_type == 'PUMA':
                raw_driver = str(row.get('driver_name', 'Unknown Driver')).strip()
                date_val = row.get('date', row.get('loading_date')) # fallback checking
                order_num = row.get('trip_id', row.get('puma_order_number', 'N/A'))
                load_pnt = row.get('load_point', 'N/A')
                off_pnt = row.get('discharge_point', 'N/A')
                truck = row.get('truck_reg', 'N/A')
                product_val = ''
                trip_id_key = None
            else:  # SECONDARY
                raw_driver = str(row.get('driver', 'Unknown Driver')).strip()
                date_val = row.get('date', row.get('date_loaded'))
                order_num = row.get('trip_id', 'N/A')
                load_pnt = row.get('loading_point', 'N/A')
                off_pnt = row.get('offloading_point', 'N/A')
                truck = row.get('truck_reg', 'N/A')
                # Pull raw product and trip_id strings for cross-row secondary deduplication
                product_val = str(row.get('product', '')).strip()
                trip_id_key = str(row.get('trip_id', '')).strip()

            # --- 2. Driver Name Normalization ---
            if not raw_driver or raw_driver.lower() in ['unknown', 'nan', 'unknown driver']:
                continue
            name_parts = sorted([part.capitalize() for part in str(raw_driver).split()])
            driver = " ".join(name_parts)

            # --- 3. Parse Dates Safely ---
            parsed_date = pd.to_datetime(date_val, format='mixed', errors='coerce')
            if pd.isna(parsed_date):
                continue

            # --- 4. Pay Cycle Logic (17th to 16th) ---
            day = parsed_date.day
            if day >= 17:
                cycle_start = parsed_date.replace(day=17)
                cycle_end = (parsed_date + pd.DateOffset(months=1)).replace(day=16)
            else:
                cycle_start = (parsed_date - pd.DateOffset(months=1)).replace(day=17)
                cycle_end = parsed_date.replace(day=16)

            year_key = str(cycle_start.year)
            month_label = f"{cycle_start.strftime('%b %d')} - {cycle_end.strftime('%b %d')}"

            # --- 5. Build Unified Hierarchical JSON ---
            if year_key not in loads_data: loads_data[year_key] = {}
            if month_label not in loads_data[year_key]: loads_data[year_key][month_label] = {}
            if driver not in loads_data[year_key][month_label]: loads_data[year_key][month_label][driver] = []

            loads_data[year_key][month_label][driver].append({
                'date': parsed_date.strftime('%Y-%m-%d'),
                'order_number': order_num,
                'loading_point': load_pnt,
                'offloading_point': off_pnt,
                'truck_reg': truck,
                'trip_type': source_type,
                'product': product_val,
                'trip_id_key': trip_id_key
            })

    # -------------------------------------------------------------------------
    # LOADING INDIVIDUAL DATASETS
    # -------------------------------------------------------------------------
    # A. Parse trips.csv (Engen Bridging Network Operations)
    engen_path = os.path.join(base_dir, 'DATA/trips.csv') if os.path.exists(os.path.join(base_dir, 'DATA/trips.csv')) else os.path.join(base_dir, 'trips.csv')
    if os.path.exists(engen_path):
        df_engen = pd.read_csv(engen_path).drop_duplicates()
        df_engen.columns = df_engen.columns.str.strip()
        process_trip_records(df_engen, 'ENGEN')

    # B. Parse secondary_trips.csv (Local Multi-Drop Routes)
    secondary_path = os.path.join(base_dir, 'DATA/secondary_trips.csv') if os.path.exists(os.path.join(base_dir, 'DATA/secondary_trips.csv')) else os.path.join(base_dir, 'secondary_trips.csv')
    if os.path.exists(secondary_path):
        df_sec = pd.read_csv(secondary_path).drop_duplicates()
        df_sec.columns = df_sec.columns.str.strip()
        process_trip_records(df_sec, 'SECONDARY')

    # C. Parse puma_trips.csv (Puma Depot Runs)
    puma_path = os.path.join(base_dir, 'DATA/puma_trips.csv') if os.path.exists(os.path.join(base_dir, 'DATA/puma_trips.csv')) else os.path.join(base_dir, 'puma_trips.csv')
    if os.path.exists(puma_path):
        df_puma = pd.read_csv(puma_path).drop_duplicates()
        df_puma.columns = df_puma.columns.str.strip()
        process_trip_records(df_puma, 'PUMA')

    # -------------------------------------------------------------------------
    # DEDUPLICATE SECONDARY TRIP_IDs & SORT DRIVERS BY MANIFEST VOLUME
    # -------------------------------------------------------------------------
    processed_loads_data = {}

    for yr, months in loads_data.items():
        processed_loads_data[yr] = {}
        for mnth, drivers in months.items():
            processed_loads_data[yr][mnth] = {}
            
            for drv, items in drivers.items():
                final_driver_trips = []
                secondary_aggregation = {}

                for item in items:
                    if item['trip_type'] == 'SECONDARY' and item['trip_id_key']:
                        t_id = item['trip_id_key']
                        prod = item['product']
                        
                        if t_id not in secondary_aggregation:
                            secondary_aggregation[t_id] = item
                            # Keep track of unique product names using a set
                            secondary_aggregation[t_id]['products_set'] = {prod} if prod else set()
                        else:
                            if prod:
                                secondary_aggregation[t_id]['products_set'].add(prod)
                    else:
                        # ENGEN and PUMA load sheets pass straight down line-by-line
                        final_driver_trips.append(item)

                # Process local multi-drop sets into a unified single row record
                for t_id, data in secondary_aggregation.items():
                    sorted_prods = sorted(list(data['products_set']))
                    if sorted_prods:
                        combined_prods = "/".join(sorted_prods)
                        # Append the combined products string to offloading point context field
                        data['offloading_point'] = f"{data['offloading_point']} ({combined_prods})"
                    
                    final_driver_trips.append(data)

                # Chronological sorting for individual manifest row dates inside this driver
                final_driver_trips = sorted(final_driver_trips, key=lambda x: x['date'])
                processed_loads_data[yr][mnth][drv] = final_driver_trips

            # HIGH-VOLUME FIRST SORTING Logic
            # Sort drivers descending based on their final combined row counts
            sorted_drivers = sorted(
                processed_loads_data[yr][mnth].items(), 
                key=lambda x: len(x[1]), 
                reverse=True
            )
            processed_loads_data[yr][mnth] = OrderedDict(sorted_drivers)

    # Sort years descending
    sorted_years = sorted(processed_loads_data.keys(), reverse=True)
    
    return render_template('loads.html', 
                           loads_data=processed_loads_data, 
                           years=sorted_years)

@app.route('/export_driver_loads/<year>/<month_label>/<format>')
@login_required
def export_driver_loads(year, month_label, format):
    # 1. Load and process exactly like your main function to ensure data parity
    try:
        trips_df = pd.read_csv('DATA/trips.csv')
    except FileNotFoundError:
        flash("Source data file not found.", "error")
        return redirect(url_for('driver_loads'))

    trips_df.columns = trips_df.columns.str.strip()
    trips_df['date_loaded'] = pd.to_datetime(trips_df['date_loaded'], format='mixed', errors='coerce')
    trips_df = trips_df.dropna(subset=['date_loaded'])
    
    report_data = []

    for _, row in trips_df.iterrows():
        # Driver Name Normalization logic (Matches your main function)
        raw_driver = str(row.get('driver', 'Unknown Driver')).strip()
        if not raw_driver or raw_driver.lower() == 'nan':
            raw_driver = "Unknown Driver"
            
        name_parts = sorted([part.capitalize() for part in raw_driver.split()])
        driver = " ".join(name_parts)
        
        # Pay Cycle Logic (17th to 16th)
        date = row['date_loaded']
        if date.day >= 17:
            cycle_start = date.replace(day=17)
            cycle_end = (date + pd.DateOffset(months=1)).replace(day=16)
        else:
            cycle_start = (date - pd.DateOffset(months=1)).replace(day=17)
            cycle_end = date.replace(day=16)

        current_label = f"{cycle_start.strftime('%b %d')} - {cycle_end.strftime('%b %d')}"
        
        # Check if this row belongs to the specific year and month_label requested
        if str(cycle_start.year) == str(year) and current_label == month_label:
            report_data.append({
                'Driver': driver,
                'Date Loaded': date.strftime('%Y-%m-%d'),
                'Order #': row.get('order_number', 'N/A'),
                'Loading Point': row.get('loading_point', 'N/A'),
                'Offloading Point': row.get('offloading_point', 'N/A'),
                'Truck Reg': row.get('truck_reg', 'N/A')
            })

    df_export = pd.DataFrame(report_data)
    
    if df_export.empty:
        flash(f"No data found for the period: {month_label}", "warning")
        return redirect(url_for('driver_loads'))
    
    # Sort for a clean report layout (By Driver, then Date)
    df_export = df_export.sort_values(by=['Driver', 'Date Loaded'])

    # -------------------- EXPORT: EXCEL --------------------
    if format == 'excel':
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_export.to_excel(writer, index=False, sheet_name='Loads')
        output.seek(0)
        return send_file(
            output, 
            as_attachment=True, 
            download_name=f"Loads_{month_label.replace(' ', '_')}_{year}.xlsx",
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    # -------------------- EXPORT: PDF --------------------
    elif format == 'pdf':
        class PDF(FPDF):
            def header(self):
                self.set_font('Arial', 'B', 14)
                self.cell(0, 10, f'Driver Loads Report: {month_label} {year}', ln=True, align='C')
                self.ln(5)

            def footer(self):
                self.set_y(-15)
                self.set_font('Arial', 'I', 8)
                self.cell(0, 10, f'Page {self.page_no()}', align='C')

        pdf = PDF(orientation='L') # Landscape for better column fit
        pdf.add_page()
        pdf.set_font("Arial", 'B', 10)
        
        # Table Header Styling (Using your UI primary blue)
        pdf.set_fill_color(37, 99, 235) 
        pdf.set_text_color(255, 255, 255)
        headers = ['Driver', 'Date', 'Order #', 'Loading Point', 'Offloading Point', 'Truck Reg']
        widths = [55, 30, 30, 55, 55, 45]
        
        for i, header in enumerate(headers):
            pdf.cell(widths[i], 10, header, border=1, fill=True, align='C')
        pdf.ln()

        # Table Rows
        pdf.set_font("Arial", '', 9)
        pdf.set_text_color(0, 0, 0)
        for _, row in df_export.iterrows():
            pdf.cell(widths[0], 10, str(row['Driver']), border=1)
            pdf.cell(widths[1], 10, str(row['Date Loaded']), border=1, align='C')
            pdf.cell(widths[2], 10, str(row['Order #']), border=1, align='C')
            pdf.cell(widths[3], 10, str(row['Loading Point']), border=1)
            pdf.cell(widths[4], 10, str(row['Offloading Point']), border=1)
            pdf.cell(widths[5], 10, str(row['Truck Reg']), border=1, align='C')
            pdf.ln()

        # FIXED PDF Stream Handling
        pdf_bytes = pdf.output(dest='S')
        # Ensure correct encoding for latin1 (PDF standard) or direct binary
        if isinstance(pdf_bytes, str):
            pdf_bytes = pdf_bytes.encode('latin1')
            
        output = io.BytesIO(pdf_bytes)
        output.seek(0)
        
        return send_file(
            output, 
            as_attachment=True, 
            download_name=f"Loads_{month_label.replace(' ', '_')}_{year}.pdf",
            mimetype='application/pdf'
        )

    return redirect(url_for('driver_loads'))

# --- EMAIL CONFIGURATION ---
SMTP_SERVER = "smtp.gmail.com" # Use "smtp-mail.outlook.com" for Outlook
SMTP_PORT = 465 # Use 587 for Outlook with starttls()
EMAIL_USER = "karabotsoeu54@gmail.com"
EMAIL_PASS = "nptg tfpp zwfz kmlb"
# Change this:
RECEIVER_EMAIL = ["operations@smsfuel.co.za", "info@smsfuel.co.za"]

def get_allowance_df():
    df_trips = pd.read_csv('DATA/trips.csv')
    df_rates = pd.read_csv('DATA/rates.csv')

    # Ensure indices are clean
    df_trips['original_index'] = df_trips.index.astype(int)

    # Standardize Status
    df_trips['allowance_status'] = df_trips['allowance_status'].fillna('PENDING').astype(str).str.upper()

    # Create cleaning keys
    df_trips['t_load'] = df_trips['loading_point'].astype(str).str.strip().str.upper()
    df_trips['t_off'] = df_trips['offloading_point'].astype(str).str.strip().str.upper()
    df_rates['t_load'] = df_rates['loading_point'].astype(str).str.strip().str.upper()
    df_rates['t_off'] = df_rates['offloading_point'].astype(str).str.strip().str.upper()

    # Merge
    df = pd.merge(df_trips, df_rates[['t_load', 't_off', 'food_allowance']].drop_duplicates(), 
                  on=['t_load', 't_off'], how='left')
    
    df['food_allowance'] = pd.to_numeric(df['food_allowance'], errors='coerce').fillna(0)
    df['original_index'] = df['original_index'].astype(int)
    
    return df

def send_allowance_email(df_to_send):
    # 1. Create the CSV attachment (as you had before)
    temp_filename = "food_allowance_request.csv"
    df_to_send.to_csv(temp_filename, index=False)
    
    msg = MIMEMultipart()
    msg['Subject'] = "TEST - FOOD ALLOWANCE REQUEST"
    msg['From'] = EMAIL_USER
    msg['To'] = ", ".join(RECEIVER_EMAIL)
    
    # 2. Build the HTML Table for the email body
    html_table = df_to_send.to_html(
        index=False, 
        border=0, 
        classes='table table-striped'
    ).replace('<thead>', '<thead style="background-color: #343a40; color: white;">') \
     .replace('<th>', '<th style="padding: 12px; text-align: left; border-bottom: 2px solid #dee2e6;">') \
     .replace('<td>', '<td style="padding: 10px; border-bottom: 1px solid #dee2e6;">')

    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333;">
        <h3 style="color: #007bff;">New Food Allowance Request</h3>
        <p>Attached is the request for <b>{len(df_to_send)}</b> loads.</p>
        <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
            {html_table}
        </table>
        <br>
        <p>Kind regards,<br><b>SMS FUEL PTY LTD</b></p>
    </body>
    </html>
    """
    
    # Attach HTML version to body
    msg.attach(MIMEText(html_body, 'html'))
    
    # 3. Attach the CSV file
    with open(temp_filename, "rb") as f:
        part = MIMEApplication(f.read(), Name=temp_filename)
        part['Content-Disposition'] = f'attachment; filename="{temp_filename}"'
        msg.attach(part)
        
    # 4. Send the email
    # Note: If your port is 587, use SMTP() + starttls(). If 465, use SMTP_SSL().
    if SMTP_PORT == 587:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
    else:
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
        
    server.login(EMAIL_USER, EMAIL_PASS)
    server.sendmail(EMAIL_USER, RECEIVER_EMAIL, msg.as_string())
    server.quit()
    
    # Clean up temp file
    if os.path.exists(temp_filename):
        os.remove(temp_filename)

@app.route('/driver/allowance')
@login_required
def driver_allowance():
    df = get_allowance_df() # Call the helper
    
    # Filter Tables
    pending = df[df['allowance_status'] == 'PENDING'].to_dict(orient='records')
    requested = df[df['allowance_status'] == 'REQUESTED'].to_dict(orient='records')
    
    return render_template('driver_allowance.html', 
                           pending=pending, 
                           requested=requested, 
                           total_requested=sum(item['food_allowance'] for item in requested),
                           pending_count=len(pending))

@app.route('/driver/request_allowance', methods=['POST'])
@login_required
def request_allowance():
    # 1. Load data
    try:
        df_trips = pd.read_csv('DATA/trips.csv')
        df_rates = pd.read_csv('DATA/rates.csv')
    except Exception as e:
        flash(f"System Error: Could not load files. {e}", "danger")
        return redirect('/driver/allowance')

    # 2. Standardize column names (strip spaces, lowercase)
    df_trips.columns = df_trips.columns.str.strip().str.lower()
    df_rates.columns = df_rates.columns.str.strip().str.lower()

    # 3. Clean statuses for filtering
    df_trips['allowance_status'] = df_trips['allowance_status'].fillna('pending').astype(str).str.strip().str.lower()

    # 4. Filter for PENDING trips
    mask = (df_trips['allowance_status'] == 'pending')
    
    # Debug: Check if mask actually finds anything
    if not mask.any():
        flash(f"No pending allowances found. Current statuses in file: {df_trips['allowance_status'].unique()}", "warning")
        return redirect('/driver/allowance')

    # 5. Create matching keys to merge with rates.csv
    
    df_trips['t_load'] = df_trips['loading_point'].astype(str).str.strip().str.upper()
    df_trips['t_off'] = df_trips['offloading_point'].astype(str).str.strip().str.upper()
    df_rates['t_load'] = df_rates['loading_point'].astype(str).str.strip().str.upper()
    df_rates['t_off'] = df_rates['offloading_point'].astype(str).str.strip().str.upper()

    # 6. Merge to get food_allowance
    to_request = pd.merge(df_trips[mask], 
                          df_rates[['t_load', 't_off', 'food_allowance']].drop_duplicates(), 
                          on=['t_load', 't_off'], how='left')

    # 7. Prepare specific email data
    try:
        df_email = pd.DataFrame()
        df_email['Driver'] = to_request['driver']
        df_email['Date'] = to_request['date_loaded']
        df_email['Order'] = to_request['order_number']
        df_email['Route'] = to_request['loading_point'].astype(str) + " → " + to_request['offloading_point'].astype(str)
        # Handle cases where allowance might be NaN (fill with 0)
        df_email['Amount'] = to_request['food_allowance'].fillna(0).apply(lambda x: "{:,.2f}".format(float(x)))
        
        # 8. Send Email
        send_allowance_email(df_email)
        
        # 9. If success, log to history and update trips.csv
        request_file = 'DATA/requested_food_allowance.csv'
        file_exists = os.path.exists(request_file)
        to_request.to_csv(request_file, mode='a', header=not file_exists, index=False)

        # Update original trips status to REQUESTED
        df_trips.loc[mask, 'allowance_status'] = 'requested'
        df_trips.to_csv('DATA/trips.csv', index=False)

        flash(f"Success! {len(to_request)} allowance(s) requested and emailed.", "success")
        
    except Exception as e:
        flash(f"Email failed: {str(e)}. No statuses were updated.", "danger")

    return redirect('/driver/allowance')
    
# --- 1. MARK SINGLE ENTRY PAID ---
@app.route('/driver/mark_single_paid/<int:idx>', methods=['POST'])
def mark_single_paid(idx):
    df_trips = pd.read_csv('DATA/trips.csv')
    ref = request.form.get('payment_ref', 'N/A')
    
    # We use .index to check if the idx exists
    if idx in df_trips.index:
        # Create the archive row
        row = df_trips.loc[[idx]].copy()
        row['payment_ref'] = ref
        row['paid_at'] = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')
        
        # Save to Archive
        row.to_csv('DATA/paid_food_allowance.csv', mode='a', index=False, 
                   header=not os.path.exists('DATA/paid_food_allowance.csv'))
        
        # Update original file
        df_trips.at[idx, 'allowance_status'] = 'PAID'
        df_trips.to_csv('DATA/trips.csv', index=False)
        
        flash(f"Payment recorded for row {idx} with Ref: {ref}", "success")
    else:
        flash(f"Error: Row index {idx} not found in trips.csv", "danger")
        
    return redirect('/driver/allowance')

# --- 2. MARK ALL REQUESTED AS PAID (BULK) ---
@app.route('/driver/mark_all_paid', methods=['POST'])
def mark_all_paid():
    df_trips = pd.read_csv('DATA/trips.csv')
    batch_ref = request.form.get('batch_ref', 'BATCH_PAY')

    mask = df_trips['allowance_status'].astype(str).str.upper() == 'REQUESTED'
    to_pay = df_trips[mask].copy()

    if not to_pay.empty:
        to_pay['payment_reference'] = batch_ref
        to_pay['payment_date'] = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')

        # Save to Archive
        to_pay.to_csv('DATA/paid_food_allowance.csv', mode='a', 
                      header=not os.path.exists('DATA/paid_food_allowance.csv'), index=False)

        # Update Main File
        df_trips.loc[mask, 'allowance_status'] = 'PAID'
        df_trips.to_csv('DATA/trips.csv', index=False)
        flash(f"Successfully marked all as PAID (Ref: {batch_ref})", "success")
    
    return redirect('/driver/allowance')
# -------------------- DOCUMENTS --------------------

@app.route("/documents")
@login_required
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

#--------------------INCIDENTS---------------------


# --- NEW ROUTES FOR INCIDENTS ---

@app.route('/incidents')
@login_required
def incidents_dashboard():
    # Load incident data
    df = pd.read_csv('DATA/incidents.csv')
    incidents = df.to_dict(orient='records')
    
    # Summaries for the Incident Dashboard
    summary = {
        'total': len(df),
        'open': len(df[df['status'] == 'OPEN']),
        'unsafe_act': len(df[df['type'] == 'Unsafe Act']),
        'unsafe_cond': len(df[df['type'] == 'Unsafe Condition'])
    }
    return render_template('incidents.html', incidents=incidents, summary=summary)

@app.route('/add-incident', methods=['POST'])
def add_incident():
    new_data = {
        'id': datetime.now().strftime('%Y%m%d%H%M%S'),
        'date': request.form.get('date'),
        'unit_id': request.form.get('unit_id'),
        'type': request.form.get('type'), 
        'reporter': request.form.get('reporter'),
        'description': str(request.form.get('description')), # Force string
        'status': 'OPEN',
        'why1': '', 'why2': '', 'why3': '', 'why4': '', 'why5': '', 
        'root_cause': '',
        'action_plan': '',
        'report_path': ''
    }
    
    csv_path = 'DATA/incidents.csv'
    
    # 1. Load existing data or create new
    if os.path.exists(csv_path):
        # dtype=object is the most "relaxed" type; it stops Pandas from guessing float64
        df = pd.read_csv(csv_path, dtype=object) 
    else:
        df = pd.DataFrame(columns=new_data.keys())
    
    # 2. Append new row
    new_row_df = pd.DataFrame([new_data])
    df = pd.concat([df, new_row_df], ignore_index=True)
    
    # 3. CRITICAL: Clean up existing data
    # This replaces any 'NaN' or float errors with empty strings before saving
    df = df.astype(str).replace('nan', '')
    
    # 4. Save
    df.to_csv(csv_path, index=False)
    
    return redirect(url_for('incidents_dashboard'))

@app.route('/delete-incident', methods=['POST'])
def delete_incident():
    incident_id = request.form.get('id')
    df = pd.read_csv('DATA/incidents.csv')
    
    # Filter out the record with the matching ID
    df = df[df['id'].astype(str) != str(incident_id)]
    
    df.to_csv('DATA/incidents.csv', index=False)
    return redirect(url_for('incidents_dashboard'))

INCIDENT_REPORTS_FOLDER = 'uploads/incidents'
os.makedirs(INCIDENT_REPORTS_FOLDER, exist_ok=True)
@app.route('/update-rca', methods=['POST'])
def update_rca():
    incident_id = str(request.form.get('incident_id'))
    report_file = request.files.get('report_file')
    
    csv_path = 'DATA/incidents.csv'
    
    if not os.path.exists(csv_path):
        flash("❌ Error: Incident database not found.", "error")
        return redirect(url_for('incidents_dashboard'))

    # 1. Load the data as OBJECTS (prevents the float64 lock)
    df = pd.read_csv(csv_path, dtype=object)
    
    # 2. MANDATORY: Force all columns to string and replace 'nan' with empty text
    # This specifically fixes the Line 1054 error
    df = df.astype(str).replace('nan', '')

    if incident_id in df['id'].values:
        # Get the row index
        idx = df[df['id'] == incident_id].index[0]
        
        # 3. Handle File Upload
        filename = ""
        if report_file and report_file.filename != '':
            filename = f"RCA_{incident_id}_{report_file.filename}"
            report_file.save(os.path.join(INCIDENT_REPORTS_FOLDER, filename))
        
        # 4. Save the 5 Whys (This is where the error was happening)
        for i in range(1, 6):
            # Using .at is now safe because we converted df to string above
            df.at[idx, f'why{i}'] = str(request.form.get(f'why{i}', ''))
        
        # 5. Save the rest of the fields
        df.at[idx, 'action_plan'] = str(request.form.get('rap', ''))
        df.at[idx, 'status'] = 'CLOSED'
        df.at[idx, 'report_path'] = filename
        
        # 6. Save back to CSV
        df.to_csv(csv_path, index=False)
        flash(f"✅ Incident {incident_id} successfully investigated and closed.", "success")
    else:
        flash("❌ Incident ID not found.", "error")
        
    return redirect(url_for('incidents_dashboard'))


@app.route('/uploads/incidents/<filename>')
@login_required
def serve_incident_report(filename):
    # This points Flask to the actual folder on your computer
    return send_from_directory('uploads/incidents', filename)
# -------------------- RUN APP --------------------

if __name__ == '__main__':
    # Use the PORT environment variable provided by Render, or default to 5000
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)