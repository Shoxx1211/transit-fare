import sqlite3
import os

# Path to DB
DB_NAME = os.path.join(os.path.dirname(__file__), 'transit_fare.db')

def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()

        # Users
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                surname TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                dob TEXT NOT NULL,
                password TEXT NOT NULL,
                card_id TEXT NOT NULL UNIQUE,
                balance REAL DEFAULT 0.0
            )
        ''')

        # Trip sessions (tap-ins only, active)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trip_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                card_id TEXT,
                fare_amount REAL DEFAULT 0.0,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (card_id) REFERENCES users(card_id)
            )
        ''')

        # Trip history (completed trips)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trip_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id TEXT NOT NULL,
                name TEXT NOT NULL,
                start_time REAL NOT NULL,
                end_time REAL NOT NULL,
                fare REAL NOT NULL,
                FOREIGN KEY (card_id) REFERENCES users(card_id)
            )
        ''')

        conn.commit()

if __name__ == "__main__":
    init_db()
    print("✅ Database initialized successfully.")
