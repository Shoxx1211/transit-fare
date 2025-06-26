import sqlite3

conn = sqlite3.connect('transit_fare.db')
cursor = conn.cursor()

# Create users table (if not already created)
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        card_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        balance REAL DEFAULT 0
    )
''')

# ✅ Create trips table for tap-in/out
cursor.execute('''
    CREATE TABLE IF NOT EXISTS trips (
        card_id TEXT PRIMARY KEY,
        start_lat REAL,
        start_lon REAL,
        start_time INTEGER,
        FOREIGN KEY (card_id) REFERENCES users(card_id)
    )
''')

conn.commit()
conn.close()
print("✅ Tables created successfully.")
