



from flask import Flask, request, render_template, redirect, url_for, g, session, jsonify
import bcrypt
import uuid
import os
import time
import math
import sqlite3
from datetime import datetime
import requests
from math import radians, cos, sin, asin, sqrt
from db import DB_NAME, init_db, get_connection
from config import (
    PAYSTACK_SECRET_KEY,
    PAYSTACK_PUBLIC_KEY,
    PAYSTACK_CALLBACK_URL,
)


app = Flask(__name__, template_folder='templates')
app.secret_key = os.urandom(24)

def calculate_distance_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    r = 6371.0  # Earth radius in km
    return c * r

def get_fare(distance_km):
    if distance_km <= 2:
        return 5.0
    elif distance_km <= 5:
        return 10.0
    elif distance_km <= 10:
        return 15.0
    else:
        return 20.0

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
    print("Looking for template at:", os.path.abspath('templates/index.html'))
    return render_template('index.html')

if __name__ == "__main__":
    app.run()
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


# Track simulated tap-in sessions
@app.route("/simulate_nfc", methods=["GET", "POST"])
def simulate_nfc():
    conn = get_db()
    cursor = conn.cursor()

    # Fetch users into a dict keyed by card_id for quick lookup
    cursor.execute("SELECT id, card_id, name || ' ' || surname AS full_name, balance FROM users")
    users = {row["card_id"]: row for row in cursor.fetchall()}

    message = None
    stage = "tap_in"  # default stage for UI

    if request.method == "POST":
        card_id = request.form.get("card_id")
        lat_str = request.form.get("lat")
        lon_str = request.form.get("lon")
        stage = request.form.get("stage")

        # Input validation
        if not card_id or lat_str is None or lon_str is None:
            message = "❌ Missing card ID or location coordinates."
            return render_template("simulate_nfc.html", users=users, message=message, stage=stage)

        try:
            lat = float(lat_str)
            lon = float(lon_str)
        except ValueError:
            message = "❌ Latitude and longitude must be valid numbers."
            return render_template("simulate_nfc.html", users=users, message=message, stage=stage)

        user = users.get(card_id)
        if not user:
            message = "❌ Card not found."
            return render_template("simulate_nfc.html", users=users, message=message, stage=stage)

        if stage == "tap_in":
            # Clear any previous unfinished trip session for this card
            conn.execute('DELETE FROM trip_sessions WHERE card_id = ?', (card_id,))

            # Insert a new trip session with current timestamp and start coordinates
            conn.execute('''
                INSERT INTO trip_sessions (card_id, start_lat, start_lon)
                VALUES (?, ?, ?)
            ''', (card_id, lat, lon))

            conn.commit()
            message = f"✅ Tap In successful for {user['full_name']}."
            stage = "tap_out"

        elif stage == "tap_out":
            # Retrieve the tap-in trip session data
            trip = conn.execute('SELECT * FROM trip_sessions WHERE card_id = ?', (card_id,)).fetchone()

            if not trip:
                message = "❌ No Tap In found. Please tap in first."
            else:
                # Calculate distance travelled
                distance_km = calculate_distance_km(trip['start_lat'], trip['start_lon'], lat, lon)
                fare = get_fare(distance_km)

                if user["balance"] < fare:
                    message = f"❌ Insufficient balance (R{user['balance']:.2f}). Fare is R{fare:.2f}."
                else:
                    new_balance = user["balance"] - fare

                    # Remove the trip session now that trip ended
                    conn.execute('DELETE FROM trip_sessions WHERE card_id = ?', (card_id,))

                    # Update user balance
                    conn.execute('UPDATE users SET balance = ? WHERE card_id = ?', (new_balance, card_id))

                    # Insert into trip history, converting timestamps to datetime strings
                    start_time_str = trip['timestamp']  # your table uses timestamp column for start time
                    end_time_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

                    conn.execute('''
                        INSERT INTO trip_history (card_id, name, start_time, end_time, fare)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (card_id, user['full_name'], start_time_str, end_time_str, fare))

                    conn.commit()
                    message = f"✅ Tap Out complete. Fare: R{fare:.2f}. New balance: R{new_balance:.2f}."
                    stage = "tap_in"  # ready for next trip

    return render_template("simulate_nfc.html", users=users, message=message, stage=stage)

@app.route("/simulate_nfc_tap_in", methods=["GET", "POST"])
def simulate_nfc_tap_in():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, card_id, name || ' ' || surname AS full_name, balance FROM users")
    users = {row["card_id"]: row for row in cursor.fetchall()}

    message = None
    if request.method == "POST":
        card_id = request.form.get("card_id")
        lat = float(request.form.get("lat"))
        lon = float(request.form.get("lon"))

        user = users.get(card_id)
        if not user:
            message = "❌ Card not found."
        else:
            # Remove any previous tap-in
            conn.execute('DELETE FROM trip_sessions WHERE card_id = ?', (card_id,))
            conn.execute('''
                INSERT INTO trip_sessions (card_id, start_time, start_lat, start_lon)
                VALUES (?, ?, ?, ?)
            ''', (card_id, time.time(), lat, lon))
            conn.commit()
            return redirect(url_for("simulate_nfc_tap_out", card_id=card_id))

    return render_template("simulate_nfc_tap_in.html", users=users, message=message)

@app.route("/simulate_nfc_tap_out", methods=["GET", "POST"])
def simulate_nfc_tap_out():
    card_id = request.args.get("card_id") or request.form.get("card_id")
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, card_id, name || ' ' || surname AS full_name, balance FROM users")
    users = {row["card_id"]: row for row in cursor.fetchall()}
    user = users.get(card_id)

    message = None
    if request.method == "POST":
        lat = float(request.form.get("lat"))
        lon = float(request.form.get("lon"))

        trip = conn.execute('SELECT * FROM trip_sessions WHERE card_id = ?', (card_id,)).fetchone()
        if not trip:
            message = "❌ No Tap In found. Please tap in first."
        else:
            distance_km = calculate_distance_km(trip["start_lat"], trip["start_lon"], lat, lon)
            fare = get_fare(distance_km)

            if user["balance"] < fare:
                message = f"❌ Insufficient balance (R{user['balance']:.2f}). Fare is R{fare:.2f}"
            else:
                new_balance = user["balance"] - fare
                conn.execute('DELETE FROM trip_sessions WHERE card_id = ?', (card_id,))
                conn.execute('UPDATE users SET balance = ? WHERE card_id = ?', (new_balance, card_id))
                conn.execute('''
                    INSERT INTO trip_history (card_id, name, start_time, end_time, fare)
                    VALUES (?, ?, ?, ?, ?)
                ''', (card_id, user['full_name'], trip['start_time'], time.time(), fare))
                conn.commit()
                message = f"✅ Tap Out complete. Fare: R{fare:.2f}. New balance: R{new_balance:.2f}"

    return render_template("simulate_nfc_tap_out.html", card_id=card_id, user=user, message=message)


@app.route('/tap_in', methods=['GET', 'POST'])
def tap_in():
    conn = get_db()

    if request.method == 'POST':
        card_id = request.form.get('card_id')
        lat = request.form.get('lat')
        lon = request.form.get('lon')

        if not card_id or not lat or not lon:
            return "❌ Card ID or Location not provided", 400

        conn.execute('DELETE FROM trip_sessions WHERE card_id = ?', (card_id,))
        conn.execute(
            'INSERT INTO trip_sessions (card_id, start_time, start_lat, start_lon) VALUES (?, ?, ?, ?)',
            (card_id, time.time(), lat, lon)
        )
        conn.commit()

        return render_template('tap_in_success.html', card_id=card_id, lat=lat, lon=lon)

    return render_template('tap_in.html')



@app.route('/tap_out', methods=['GET', 'POST'])
def tap_out():
    conn = get_db()

    if request.method == 'POST':
        card_id = request.form.get('card_id')
        lat2 = request.form.get('lat')
        lon2 = request.form.get('lon')

        if not card_id or not lat2 or not lon2:
            return "❌ Card ID or Location not provided", 400

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

    return render_template('tap_out.html')


@app.route('/test_tap_out', methods=['POST'])
def test_tap_out():
    print("Tap out route hit!")
    return "OK"

# ------------------------------ PAYSTACK ------------------------------ #
PAYSTACK_BASE_URL = 'https://api.paystack.co'

def _build_callback_url():
    """
    Return the live callback URL to give Paystack.
    We prefer config constant, but if missing, fall back to Flask url_for.
    """
    if PAYSTACK_CALLBACK_URL:
        return PAYSTACK_CALLBACK_URL
    # fallback (rare); ensure https
    try:
        return url_for('payment_callback', _external=True, _scheme='https')
    except RuntimeError:
        # no request context
        return 'https://tethnix1211.pythonanywhere.com/payment/callback'


@app.route('/top_up/<card_id>', methods=['GET', 'POST'])
def top_up(card_id):
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE card_id = ?', (card_id,)).fetchone()
    if not user:
        return "User not found", 404

    if request.method == 'POST':
        raw_amount = request.form.get('amount', '').strip()
        try:
            amount = float(raw_amount)
            if amount <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return "❌ Please enter a valid amount", 400

        headers = {
            'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}',
            'Content-Type': 'application/json'
        }

        payload = {
            'email': user['email'],
            'amount': int(amount * 100),   # Rands to cents
            'currency': 'ZAR',
            'metadata': {'card_id': card_id},
            'callback_url': PAYSTACK_CALLBACK_URL,  # Use the config constant directly
        }

        try:
            resp = requests.post(f'{PAYSTACK_BASE_URL}/transaction/initialize',
                                 json=payload, headers=headers, timeout=30)
        except requests.RequestException as e:
            print(f"[PAYSTACK][INIT][ERROR] {e}")
            return "❌ Failed to contact payment processor", 502

        if resp.status_code != 200:
            print(f"[PAYSTACK][INIT][HTTP {resp.status_code}] {resp.text}")
            return "❌ Failed to initiate payment", 502

        body = resp.json()
        payment_url = body.get('data', {}).get('authorization_url')
        if not payment_url:
            print(f"[PAYSTACK][INIT][MALFORMED] {body}")
            return "❌ Payment init response malformed", 502

        return redirect(payment_url)

    return render_template('top_up.html', user=user, paystack_public_key=PAYSTACK_PUBLIC_KEY)

@app.route('/payment/callback')
def payment_callback():
    """
    Paystack redirects the user here after payment.
    We verify the transaction server‑to‑server, validate currency (ZAR),
    extract the card_id from metadata, credit the wallet exactly once,
    and show a success/failure page.
    """
    reference = (request.args.get('reference') or '').strip()
    if not reference:
        return "❌ No payment reference provided.", 400

    print(f"[PAYSTACK][CALLBACK] reference={reference}")

    # Verify with Paystack
    headers = {'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}'}
    try:
        resp = requests.get(
            f'{PAYSTACK_BASE_URL}/transaction/verify/{reference}',
            headers=headers,
            timeout=30
        )
    except requests.RequestException as e:
        print(f"[PAYSTACK][VERIFY][ERROR] {e}")
        return "❌ Could not verify payment (network error).", 502

    if resp.status_code != 200:
        print(f"[PAYSTACK][VERIFY][HTTP {resp.status_code}] {resp.text}")
        return "❌ Could not verify payment (bad response).", 502

    body = resp.json()
    data = body.get('data') or {}
    status = data.get('status')
    currency = data.get('currency')
    amount_subunits = data.get('amount')  # cents
    metadata = data.get('metadata') or {}
    card_id = metadata.get('card_id')
    paid_at = data.get('paid_at')  # ISO string from Paystack (may be None)

    print(f"[PAYSTACK][VERIFY] status={status} currency={currency} "
          f"amount_subunits={amount_subunits} card_id={card_id}")

    # Basic validations
    if status != 'success':
        return "❌ Payment was not successful.", 400
    if currency != 'ZAR':
        return f"❌ Payment currency mismatch (expected ZAR, got {currency}).", 400
    if card_id is None:
        print(f"[PAYSTACK][VERIFY][WARN] Missing card_id in metadata for ref={reference}")
        return "❌ Missing card reference in payment metadata.", 400

    # Convert cents to Rands safely
    try:
        amount = float(amount_subunits) / 100.0
    except (TypeError, ValueError):
        print(f"[PAYSTACK][VERIFY][WARN] Bad amount in response: {amount_subunits!r}")
        return "❌ Invalid amount returned by payment processor.", 400

    conn = get_db()

    # --- OPTIONAL: ensure we have a topups table for idempotency ---
    # This CREATE TABLE IF NOT EXISTS is cheap in SQLite; safe to leave here.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS topups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference TEXT UNIQUE,
            card_id TEXT,
            amount REAL,
            status TEXT,
            paid_at TEXT
        )
    """)

    # If we've already processed this Paystack reference successfully, don't re‑credit.
    existing = conn.execute(
        "SELECT * FROM topups WHERE reference = ? AND status = 'success'",
        (reference,)
    ).fetchone()

    if existing:
        print(f"[PAYSTACK][IDEMPOTENT] reference {reference} already processed; skipping re‑credit.")
        # Show current balance
        user = conn.execute('SELECT * FROM users WHERE card_id = ?', (existing['card_id'],)).fetchone()
        if not user:
            return "❌ (Previously processed) user not found.", 404
        return render_template(
            'payment_success.html',
            card_id=existing['card_id'],
            amount=existing['amount'],
            balance=user['balance']
        )

    # Credit user
    user = conn.execute('SELECT * FROM users WHERE card_id = ?', (card_id,)).fetchone()
    if not user:
        print(f"[PAYSTACK][VERIFY][ERR] User with card_id {card_id} not found.")
        return "❌ User not found.", 404

    new_balance = (user['balance'] or 0) + amount

    # Update wallet + record topup in one transaction
    try:
        conn.execute('UPDATE users SET balance = ? WHERE card_id = ?', (new_balance, card_id))
        conn.execute(
            "INSERT OR IGNORE INTO topups (reference, card_id, amount, status, paid_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (reference, card_id, amount, 'success', paid_at)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[PAYSTACK][DB][ERROR] {e}")
        return "❌ Failed to update wallet after payment.", 500

    print(f"[PAYSTACK][CREDITED] card_id={card_id} +R{amount:.2f} => balance R{new_balance:.2f}")

    return render_template(
        'payment_success.html',
        card_id=card_id,
        amount=amount,
        balance=new_balance
    )


# ------------------------------ MAIN ------------------------------ #
if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
