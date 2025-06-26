# main.py

import uuid
import time
from db import init_db, get_connection

FARE_FLAT_RATE = 25.0

# -----------------------------
# Core Functions
# -----------------------------

def generate_card_id() -> str:
    return str(uuid.uuid4())

def register_user(name: str):
    """Register a new user and save to DB"""
    card_id = generate_card_id()
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO users (card_id, name, balance, in_trip) VALUES (?, ?, ?, ?)", 
              (card_id, name, 0.0, 0))
    conn.commit()
    conn.close()
    print(f"[✅] User '{name}' registered. Card ID: {card_id}")
    return card_id

def load_money(card_id: str, amount: float):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE card_id = ?", (card_id,))
    row = c.fetchone()
    if not row:
        print("[❌] Card not found.")
        return
    new_balance = row[0] + amount
    c.execute("UPDATE users SET balance = ? WHERE card_id = ?", (new_balance, card_id))
    conn.commit()
    conn.close()
    print(f"[💰] R{amount:.2f} loaded. New balance: R{new_balance:.2f}")

def check_balance(card_id: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT name, balance FROM users WHERE card_id = ?", (card_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        print("[❌] Card not found.")
    else:
        print(f"[💳] {row[0]}'s balance: R{row[1]:.2f}")

def tap_in(card_id: str):
    conn = get_connection()
    c = conn.cursor()

    c.execute("SELECT name, in_trip FROM users WHERE card_id = ?", (card_id,))
    row = c.fetchone()
    if not row:
        print("[❌] Card not found.")
        conn.close()
        return
    name, in_trip = row
    if in_trip:
        print("[⚠️] Already tapped in.")
        conn.close()
        return

    start_time = time.time()
    c.execute("INSERT OR REPLACE INTO trip_sessions (card_id, start_time) VALUES (?, ?)", (card_id, start_time))
    c.execute("UPDATE users SET in_trip = 1 WHERE card_id = ?", (card_id,))
    conn.commit()
    conn.close()
    print(f"[🚌] {name} tapped in.")

def tap_out(card_id: str):
    conn = get_connection()
    c = conn.cursor()

    # Validate user and trip status
    c.execute("SELECT name, balance, in_trip FROM users WHERE card_id = ?", (card_id,))
    user = c.fetchone()
    if not user:
        print("[❌] Card not found.")
        conn.close()
        return
    name, balance, in_trip = user
    if not in_trip:
        print("[⚠️] You haven't tapped in.")
        conn.close()
        return
    if balance < FARE_FLAT_RATE:
        print("[💸] Insufficient funds. Please load more money.")
        conn.close()
        return

    # Get start time and compute trip
    c.execute("SELECT start_time FROM trip_sessions WHERE card_id = ?", (card_id,))
    trip = c.fetchone()
    if not trip:
        print("[⚠️] No active trip found.")
        conn.close()
        return
    start_time = trip[0]
    end_time = time.time()

    # Log the trip
    c.execute('''
        INSERT INTO trip_history (card_id, name, start_time, end_time, fare)
        VALUES (?, ?, ?, ?, ?)
    ''', (card_id, name, start_time, end_time, FARE_FLAT_RATE))

    # Deduct fare and reset trip status
    new_balance = balance - FARE_FLAT_RATE
    c.execute("UPDATE users SET balance = ?, in_trip = 0 WHERE card_id = ?", (new_balance, card_id))
    c.execute("DELETE FROM trip_sessions WHERE card_id = ?", (card_id,))

    conn.commit()
    conn.close()

    print(f"[✅] {name} tapped out. Fare R{FARE_FLAT_RATE:.2f} deducted. Remaining balance: R{new_balance:.2f}")

def view_trip_history(card_id: str):
    conn = get_connection()
    c = conn.cursor()

    c.execute("SELECT name FROM users WHERE card_id = ?", (card_id,))
    row = c.fetchone()
    if not row:
        print("[❌] Card not found.")
        conn.close()
        return
    name = row[0]

    c.execute("SELECT start_time, end_time, fare FROM trip_history WHERE card_id = ? ORDER BY end_time DESC", (card_id,))
    trips = c.fetchall()
    conn.close()

    print(f"\n📜 Trip history for {name}:")
    if not trips:
        print("No trips recorded.")
        return
    for start, end, fare in trips:
        print(f"🕓 {time.ctime(start)} → {time.ctime(end)} | Fare: R{fare:.2f}")

# -----------------------------
# CLI Menu
# -----------------------------

def main_menu():
    while True:
        print("\n=== 🚍 Transit Fare System ===")
        print("1. Register User")
        print("2. Load Money")
        print("3. Check Balance")
        print("4. Tap In")
        print("5. Tap Out")
        print("6. View Trip History")
        print("0. Exit")

        choice = input("Enter choice: ")

        if choice == "1":
            name = input("Enter name: ")
            register_user(name)
        elif choice == "2":
            card_id = input("Enter Card ID: ")
            amount = float(input("Enter amount to load: R"))
            load_money(card_id, amount)
        elif choice == "3":
            card_id = input("Enter Card ID: ")
            check_balance(card_id)
        elif choice == "4":
            card_id = input("Enter Card ID: ")
            tap_in(card_id)
        elif choice == "5":
            card_id = input("Enter Card ID: ")
            tap_out(card_id)
        elif choice == "6":
            card_id = input("Enter Card ID: ")
            view_trip_history(card_id)
        elif choice == "0":
            print("👋 Goodbye!")
            break
        else:
            print("[❗] Invalid option. Try again.")

# -----------------------------
# Main
# -----------------------------

if __name__ == "__main__":
    init_db()
    main_menu()
