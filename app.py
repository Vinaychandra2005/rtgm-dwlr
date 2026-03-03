import os
import sqlite3
from flask import Flask, render_template, request, jsonify
import requests

# =====================================================
# CONFIG
# =====================================================

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "groundwater_light.db")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")


# =====================================================
# DATABASE CONNECTION
# =====================================================

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# =====================================================
# BASIC ROUTES
# =====================================================

@app.route("/")
def home():
    return render_template("logo.html")


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.route("/monitoring")
def monitoring():
    return render_template("monitoring.html")


@app.route("/support")
def support():
    return render_template("support.html")


# =====================================================
# DATA FUNCTIONS
# =====================================================

def get_latest_reading(station_name):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT station, water_level_m, date
        FROM latest_data
        WHERE station LIKE ?
        LIMIT 1
    """, (f"%{station_name}%",))

    row = cursor.fetchone()
    conn.close()

    if row:
        return f"""
Station: {row['station']}
Latest Water Level: {row['water_level_m']} meters
Timestamp: {row['date']}
"""
    return None


def get_trend(station_name):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT date, water_level_m
        FROM monthly_data
        WHERE station LIKE ?
        ORDER BY date
    """, (f"%{station_name}%",))

    rows = cursor.fetchall()
    conn.close()

    if len(rows) < 2:
        return None

    first = rows[0]["water_level_m"]
    last = rows[-1]["water_level_m"]

    if last > first:
        trend = "Rising"
    elif last < first:
        trend = "Declining"
    else:
        trend = "Stable"

    return f"""
Station: {station_name}
Trend: {trend}
Period: {rows[0]['date']} to {rows[-1]['date']}
"""


# =====================================================
# AI CHAT ROUTE
# =====================================================

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json()
        user_message = data.get("message", "").lower()

        if not user_message:
            return jsonify({"reply": "Please enter a question."})

        # Simple rule-based detection
        station_detected = None

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT station FROM latest_data")
        stations = [row["station"].lower() for row in cursor.fetchall()]
        conn.close()

        for station in stations:
            if station in user_message:
                station_detected = station
                break

        dataset_context = None

        if station_detected:
            if "latest" in user_message:
                dataset_context = get_latest_reading(station_detected)
            elif "trend" in user_message:
                dataset_context = get_trend(station_detected)

        system_prompt = """
You are an AI assistant for the Real Time Ground Water Monitoring System (RTGM DWLR).

Important:
- DWLR stands for Digital Water Level Recorder.
- It records groundwater levels at 6-hour intervals.
- Provide technical and scientific answers.
- Do not fabricate numbers.
"""

        messages = [
            {"role": "system", "content": system_prompt}
        ]

        if dataset_context:
            messages.append({"role": "system", "content": dataset_context})

        messages.append({"role": "user", "content": user_message})

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "openrouter/auto",
                "messages": messages,
                "temperature": 0.3
            },
            timeout=20
        )

        if response.status_code != 200:
            return jsonify({"reply": "AI service error."})

        result = response.json()
        reply = result["choices"][0]["message"]["content"]

        return jsonify({"reply": reply})

    except Exception as e:
        return jsonify({"reply": "AI service temporarily unavailable."})


# =====================================================
# RUN (LOCAL ONLY)
# =====================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)