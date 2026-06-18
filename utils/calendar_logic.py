import sqlite3
import pandas as pd
import os

DB_PATH = 'fleet.db'
CSV_PATH = 'calendar.csv'

def load_calendar_events():
    events = []
    
    # OPTION A: SQLite (Recommended)
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row # This lets us access columns by name
            cursor = conn.cursor()
            
            # Create table if it doesn't exist yet
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS calendar (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT,
                    title TEXT,
                    event_date TEXT,
                    notes TEXT
                )
            ''')
            
            cursor.execute("SELECT * FROM calendar ORDER BY event_date ASC")
            rows = cursor.fetchall()
            events = [dict(row) for row in rows]
            conn.close()
            return events
        except Exception as e:
            print(f"Database error: {e}")

    # OPTION B: CSV Fallback (If SQL fails or isn't ready)
    if os.path.exists(CSV_PATH):
        df = pd.read_csv(CSV_PATH)
        return df.to_dict('records')
    
    return []