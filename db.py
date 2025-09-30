import sqlite3
from contextlib import contextmanager
from datetime import datetime

# Database file
DB_NAME = "transit_fare.db"


# --------------------------
# Connection Management
# --------------------------
@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # return dict-like rows
    try:
        yield conn
    finally:
        conn.commit()
        conn.close()


# --------------------------
# Database Initialization
# --------------------------
def init_db():
    with get_connection() as conn:
        cur = conn.cursor()

        # USERS TABLE
        cur.execute("""
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
        """)

        # VIRTUAL CARDS TABLE
        cur.execute("""
        CREATE TABLE IF NOT EXISTS virtual_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id TEXT NOT NULL UNIQUE,
            user_id INTEGER NOT NULL,
            balance REAL DEFAULT 0.0,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """)

        # TRIP HISTORY TABLE
        cur.execute("""
        CREATE TABLE IF NOT EXISTS trip_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            card_id TEXT NOT NULL,
            tap_in_lat REAL,
            tap_in_lng REAL,
            tap_in_time TEXT,
            tap_out_lat REAL,
            tap_out_lng REAL,
            tap_out_time TEXT,
            fare REAL DEFAULT 0.0,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(card_id) REFERENCES virtual_cards(card_id) ON DELETE CASCADE
        )
        """)

        # TRIP SESSIONS TABLE
        cur.execute("""
        CREATE TABLE IF NOT EXISTS trip_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id TEXT NOT NULL,
            start_time TEXT NOT NULL,
            start_lat REAL NOT NULL,
            start_lon REAL NOT NULL
        )
        """)

        # TRANSACTIONS TABLE (Top-ups + Deductions)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            card_id TEXT NOT NULL,
            amount REAL NOT NULL,
            type TEXT CHECK(type IN ('topup', 'fare', 'refund')) NOT NULL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(card_id) REFERENCES virtual_cards(card_id) ON DELETE CASCADE
        )
        """)


# --------------------------
# User & Card Management
# --------------------------
def create_user(name, surname, email, dob, password, card_id):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO users (name, surname, email, dob, password, card_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (name, surname, email, dob, password, card_id))
        return cur.lastrowid


def create_virtual_card(user_id, card_id):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO virtual_cards (card_id, user_id) VALUES (?, ?)
        """, (card_id, user_id))
        return cur.lastrowid


def get_user_by_email(email):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email = ?", (email,))
        return cur.fetchone()


def get_cards_by_user(user_id):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM virtual_cards WHERE user_id = ?", (user_id,))
        return cur.fetchall()


# --------------------------
# Balance & Transactions
# --------------------------
def record_transaction(user_id, card_id, amount, type_):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO transactions (user_id, card_id, amount, type)
        VALUES (?, ?, ?, ?)
        """, (user_id, card_id, amount, type_))


def update_balance(card_id, amount, type_):
    """Updates balance and records a transaction"""
    with get_connection() as conn:
        cur = conn.cursor()

        # Get user_id from card
        cur.execute("SELECT user_id FROM virtual_cards WHERE card_id = ?", (card_id,))
        card = cur.fetchone()
        if not card:
            raise ValueError("Card not found")

        user_id = card["user_id"]

        # Update balance
        if type_ == "topup":
            cur.execute("UPDATE virtual_cards SET balance = balance + ? WHERE card_id = ?", (amount, card_id))
            cur.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id))
        elif type_ == "fare":
            cur.execute("UPDATE virtual_cards SET balance = balance - ? WHERE card_id = ?", (amount, card_id))
            cur.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (amount, user_id))

        # Record transaction
        record_transaction(user_id, card_id, amount, type_)


def get_transactions(card_id):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM transactions WHERE card_id = ? ORDER BY timestamp DESC", (card_id,))
        return cur.fetchall()


def get_total_topped_up(user_id):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
        SELECT SUM(amount) as total
        FROM transactions
        WHERE user_id = ? AND type = 'topup'
        """, (user_id,))
        row = cur.fetchone()
        return row["total"] if row and row["total"] else 0.0


# --------------------------
# Trips
# --------------------------
def start_trip(card_id, lat, lon):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO trip_sessions (card_id, start_time, start_lat, start_lon)
        VALUES (?, ?, ?, ?)
        """, (card_id, datetime.now().isoformat(), lat, lon))
        return cur.lastrowid


def end_trip(card_id, lat, lon, fare, user_id):
    with get_connection() as conn:
        cur = conn.cursor()

        # Find active session
        cur.execute("SELECT * FROM trip_sessions WHERE card_id = ? ORDER BY id DESC LIMIT 1", (card_id,))
        session = cur.fetchone()
        if not session:
            raise ValueError("No active trip session for this card")

        # Insert into trip_history
        cur.execute("""
        INSERT INTO trip_history (user_id, card_id, tap_in_lat, tap_in_lng, tap_in_time,
                                  tap_out_lat, tap_out_lng, tap_out_time, fare)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            card_id,
            session["start_lat"],
            session["start_lon"],
            session["start_time"],
            lat,
            lon,
            datetime.now().isoformat(),
            fare
        ))

        # Deduct fare
        update_balance(card_id, fare, "fare")

        # Delete session
        cur.execute("DELETE FROM trip_sessions WHERE id = ?", (session["id"],))


# --------------------------
# Initialize DB on Import
# --------------------------
init_db()
