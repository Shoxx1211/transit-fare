import sqlite3

conn = sqlite3.connect('transit_fare.db')
cursor = conn.cursor()

cursor.execute("SELECT * FROM users")
rows = cursor.fetchall()

for row in rows:
    print(f"Card ID: {row[0]}, Name: {row[1]}, Balance: R{row[2]:.2f}")

conn.close()
