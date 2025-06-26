import sqlite3

conn = sqlite3.connect('transit_fare.db')  # Use your actual DB filename
cursor = conn.cursor()

try:
    cursor.execute("ALTER TABLE trip_sessions ADD COLUMN start_lat REAL;")
    print("✅ Added start_lat column")
except sqlite3.OperationalError as e:
    print("⚠️ start_lat may already exist:", e)

try:
    cursor.execute("ALTER TABLE trip_sessions ADD COLUMN start_lon REAL;")
    print("✅ Added start_lon column")
except sqlite3.OperationalError as e:
    print("⚠️ start_lon may already exist:", e)

conn.commit()
conn.close()
