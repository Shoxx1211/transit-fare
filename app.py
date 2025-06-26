from flask import Flask, request, render_template, redirect, url_for, g, session, jsonify
import bcrypt
import uuid
import os
import time
import math
import sqlite3
from datetime import datetime
import requests

from db import DB_NAME, init_db, get_connection
from config import PAYSTACK_SECRET_KEY

app = Flask(__name__)
app.secret_key = os.urandom(24)

# ------------------------------ DB HANDLING ------------------------------ #
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_NAME)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db:
        db.close()

# ------------------------------ HELPERS ------------------------------ #
def calculate_distance_km(lat1, lon1, lat2, lon2):
    R = 6371
    lat1, lon1, lat2, lon2 = map(math.radians, [float(lat1), float(lon1), float(lat2), float(lon2)])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    return R * c

def get_fare(distance_km):
    if distance_km <= 5:
        return 12
    elif distance_km <= 10:
        return 18
    else:
        return 25

# ------------------------------ ROUTES ------------------------------ #
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    conn = get_db()
    message = None

    if request.method == 'POST':
        name = request.form.get('name')
        surname = request.form.get('surname')
        email = request.form.get('email')
        dob = request.form.get('dob')
        password = request.form.get('password')

        if not all([name, surname, email, dob, password]):
            message = "❌ All fields are required."
        else:
            hashed_pw = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            card_id = f"CARD-{uuid.uuid4().hex[:8].upper()}"

            try:
                conn.execute('''
                    INSERT INTO users (name, surname, email, dob, password, card_id, balance)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (name, surname, email, dob, hashed_pw, card_id, 0.0))
                conn.commit()
                session['card_id'] = card_id
                return redirect(url_for('dashboard', card_id=card_id))
            except sqlite3.IntegrityError:
                message = "❌ Email already registered. <a href='/login'>Login here</a>"

    return render_template('register.html', message=message)

@app.route('/login', methods=['GET', 'POST'])
def login():
    conn = get_db()
    message = None

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user and bcrypt.checkpw(password.encode(), user['password'].encode()):
            session['card_id'] = user['card_id']
            return redirect(url_for('dashboard', card_id=user['card_id']))
        else:
            message = "❌ Invalid credentials."

    return render_template('login.html', message=message)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard/<card_id>')
def dashboard(card_id):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE card_id = ?", (card_id,)).fetchone()
    if not user:
        return "User not found", 404
    return render_template("dashboard.html", user=user)

@app.template_filter('datetimeformat')
def datetimeformat(value, format='full'):
    try:
        dt = datetime.fromtimestamp(value)
        return dt.strftime('%Y-%m-%d' if format == 'date' else '%Y-%m-%d %H:%M:%S')
    except:
        return "Invalid"

@app.route('/history/<card_id>')
def trip_history(card_id):
    conn = get_db()
    trips = conn.execute(
        "SELECT * FROM trip_history WHERE card_id = ? ORDER BY start_time DESC", 
        (card_id,)
    ).fetchall()
    return render_template('trip_history.html', trips=trips)

@app.route('/nfc')
def nfc_page():
    return render_template("nfc_tap.html")

@app.route('/nfc_tap', methods=['POST'])
def nfc_tap():
    data = request.get_json()
    card_id = data.get("card_id")

    if not card_id:
        return jsonify(message="❌ No card ID provided"), 400

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE card_id = ?", (card_id,)).fetchone()

    if not user:
        return jsonify(message="❌ Card not recognized"), 404

    current_trip = conn.execute("SELECT * FROM trip_sessions WHERE card_id = ?", (card_id,)).fetchone()
    now = time.time()
    fare = 12  # Flat rate in Rands

    if not current_trip:
        # Tap-in: Start trip
        conn.execute("INSERT INTO trip_sessions (card_id, start_time) VALUES (?, ?)", (card_id, now))
        conn.commit()
        return jsonify(message=f"✅ Tap-In Successful for {user['name']}")
    else:
        # Tap-out: Complete trip
        duration = now - current_trip['start_time']

        if user['balance'] < fare:
            return jsonify(
                message=f"❌ Insufficient balance for {user['name']} (R{user['balance']:.2f}). Fare is R{fare:.2f}"
            ), 400

        new_balance = user['balance'] - fare

        conn.execute("DELETE FROM trip_sessions WHERE card_id = ?", (card_id,))
        conn.execute("UPDATE users SET balance = ? WHERE card_id = ?", (new_balance, card_id))
        conn.execute('''
    INSERT INTO trip_history (card_id, name, start_time, end_time, fare)
    VALUES (?, ?, ?, ?, ?)
''', (card_id, user['name'], current_trip['start_time'], now, fare))
@app.route("/simulate_nfc", methods=["GET", "POST"])
def simulate_nfc():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, card_id, name || ' ' || surname AS full_name, balance FROM users")
    rows = cursor.fetchall()

    users = {row["card_id"]: row for row in rows}
    message = None

    if request.method == "POST":
        card_id = request.form.get("card_id")
        start_lat = float(request.form.get("start_lat", 0))
        start_lon = float(request.form.get("start_lon", 0))
        end_lat = float(request.form.get("end_lat", 0))
        end_lon = float(request.form.get("end_lon", 0))

        user = users.get(card_id)
        if user:
            distance_km = calculate_distance_km(start_lat, start_lon, end_lat, end_lon)
            fare = get_fare(distance_km)
            if user["balance"] >= fare:
                new_balance = user["balance"] - fare
                cursor.execute("UPDATE users SET balance = ? WHERE id = ?", (new_balance, user["id"]))
                cursor.execute(
                    "INSERT INTO trip_sessions (user_id, card_id, fare_amount) VALUES (?, ?, ?)",
                    (user["id"], card_id, fare)
                )
                conn.commit()
                message = f"✅ Fare deducted: R{fare}. Distance: {distance_km:.2f} km. New balance for {user['full_name']}: R{new_balance}"
            else:
                message = f"❌ Insufficient balance for {user['full_name']} (R{user['balance']})"
        else:
            message = "❌ Card ID not found."

    return render_template(
        "simulate_nfc.html", 
        users={cid: u["full_name"] for cid, u in users.items()}, 
        message=message
    )

# Modify your `/tap_in/<card_id>` route to store GPS location
@app.route('/tap_in/<card_id>', methods=['GET', 'POST'])
def tap_in(card_id):
    conn = get_db()

    if request.method == 'POST':
        lat = request.form.get('lat')
        lon = request.form.get('lon')

        if not lat or not lon:
            return "❌ Location not provided", 400

        conn.execute('DELETE FROM trip_sessions WHERE card_id = ?', (card_id,))
        conn.execute(
            'INSERT INTO trip_sessions (card_id, start_time, start_lat, start_lon) VALUES (?, ?, ?, ?)',
            (card_id, time.time(), lat, lon)
        )
        conn.commit()

        return render_template('tap_in_success.html', card_id=card_id, lat=lat, lon=lon)

    return render_template('tap_in.html', card_id=card_id)


# Modify your `/tap_out/<card_id>` route to calculate distance-based fare
@app.route('/tap_out/<card_id>', methods=['GET', 'POST'])
def tap_out(card_id):
    conn = get_db()

    if request.method == 'POST':
        print("[DEBUG] Tap-out POST request received")
        lat2 = request.form.get('lat')
        lon2 = request.form.get('lon')

        if not lat2 or not lon2:
            return "❌ Location not provided", 400

        trip = conn.execute('SELECT * FROM trip_sessions WHERE card_id = ?', (card_id,)).fetchone()
        if not trip:
            return "❌ No tap-in found. Please tap in first.", 400

        user = conn.execute('SELECT * FROM users WHERE card_id = ?', (card_id,)).fetchone()
        if not user:
            return "❌ User not found.", 404

        distance_km = calculate_distance_km(trip['start_lat'], trip['start_lon'], lat2, lon2)
        fare = get_fare(distance_km)

        if user['balance'] < fare:
            return f"❌ Insufficient balance (R{user['balance']:.2f}). Fare is R{fare}", 400

        new_balance = user['balance'] - fare
        conn.execute('DELETE FROM trip_sessions WHERE card_id = ?', (card_id,))
        conn.execute('UPDATE users SET balance = ? WHERE card_id = ?', (new_balance, card_id))
        conn.execute('''
            INSERT INTO trip_history (card_id, name, start_time, end_time, fare)
            VALUES (?, ?, ?, ?, ?)
        ''', (card_id, user['name'], trip['start_time'], time.time(), fare))
        conn.commit()

        return render_template('tap_out_success.html', card_id=card_id, fare=fare, balance=new_balance)

    return render_template('tap_out.html', card_id=card_id)

@app.route('/test_tap_out', methods=['POST'])
def test_tap_out():
    print("Tap out route hit!")
    return "OK"

# ------------------------------ PAYSTACK ------------------------------ #
PAYSTACK_BASE_URL = 'https://api.paystack.co'

@app.route('/top_up/<card_id>', methods=['GET', 'POST'])
def top_up(card_id):
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE card_id = ?', (card_id,)).fetchone()

    if not user:
        return "User not found", 404

    if request.method == 'POST':
        amount = float(request.form.get('amount', 0))
        email = user['email']

        if amount <= 0:
            return "❌ Please enter a valid amount", 400

        headers = {
            'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}',
            'Content-Type': 'application/json'
        }

        data = {
            'email': email,
            'amount': int(amount * 100),
            'currency': 'ZAR',
            'metadata': {'card_id': card_id},
            'callback_url': 'https://4901-41-150-250-231.ngrok-free.app/payment/callback'
        }

        response = requests.post(f'{PAYSTACK_BASE_URL}/transaction/initialize', json=data, headers=headers)

        if response.status_code == 200:
            payment_url = response.json()['data']['authorization_url']
            return redirect(payment_url)
        else:
            return "❌ Failed to initiate payment", 500

    return render_template('top_up.html', user=user)

@app.route('/payment/callback')
def payment_callback():
    reference = request.args.get('reference')
    if not reference:
        return "❌ No payment reference provided", 400

    headers = {'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}'}
    response = requests.get(f'{PAYSTACK_BASE_URL}/transaction/verify/{reference}', headers=headers)

    if response.status_code == 200:
        data = response.json()['data']

        if data['status'] != 'success':
            return "❌ Payment was not successful", 400

        # Check currency is ZAR
        if data.get('currency') != 'ZAR':
            return "❌ Payment currency mismatch", 400

        amount = data['amount'] / 100  # Convert from kobo/cents to rands
        card_id = data['metadata']['card_id']

        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE card_id = ?', (card_id,)).fetchone()

        if user:
            new_balance = user['balance'] + amount
            conn.execute('UPDATE users SET balance = ? WHERE card_id = ?', (new_balance, card_id))
            conn.commit()
            return render_template('payment_success.html', card_id=card_id, amount=amount, balance=new_balance)
        else:
            return "❌ User not found", 404
    else:
        return "❌ Payment verification failed", 400

# ------------------------------ MAIN ------------------------------ #
if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
