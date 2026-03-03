import os
import sqlite3
from flask import Flask, render_template, request, jsonify, Response
import requests
import csv
from io import StringIO

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


@app.route("/support")
def support():
    return render_template("support.html")


# =====================================================
# MONITORING ROUTE
# =====================================================

@app.route("/monitoring")
def monitoring():

    conn = get_connection()
    cursor = conn.cursor()

    selected_district = request.args.get("district")
    selected_station = request.args.get("station")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    # Load districts
    cursor.execute("SELECT DISTINCT district FROM station_metadata ORDER BY district")
    districts = [row["district"] for row in cursor.fetchall()]

    stations = []
    dates = []
    water_levels = []

    latitude = None
    longitude = None

    min_level = 0
    max_level = 0
    avg_level = 0
    latest_level = 0
    total_records = 0

    # Load stations for selected district
    if selected_district:
        cursor.execute(
            "SELECT station FROM station_metadata WHERE district=? ORDER BY station",
            (selected_district,)
        )
        stations = [row["station"] for row in cursor.fetchall()]

    # Load station data
    if selected_station:

        # Coordinates
        cursor.execute(
            "SELECT latitude, longitude FROM station_metadata WHERE station=?",
            (selected_station,)
        )
        loc = cursor.fetchone()

        if loc:
            latitude = loc["latitude"]
            longitude = loc["longitude"]

        # Query monthly data
        query = """
            SELECT date, water_level_m
            FROM daily_data
            WHERE station=?
        """
        params = [selected_station]

        if start_date and end_date:
            query += " AND date BETWEEN ? AND ?"
            params.extend([start_date, end_date])

        query += " ORDER BY date"

        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()

        dates = [r["date"] for r in rows]
        water_levels = [r["water_level_m"] for r in rows]

        if water_levels:
            min_level = round(min(water_levels), 2)
            max_level = round(max(water_levels), 2)
            avg_level = round(sum(water_levels) / len(water_levels), 2)
            latest_level = round(water_levels[-1], 2)
            total_records = len(water_levels)

    conn.close()

    return render_template(
        "monitoring.html",
        districts=districts,
        stations=stations,
        selected_district=selected_district,
        selected_station=selected_station,
        start_date=start_date,
        end_date=end_date,
        dates=dates,
        water_levels=water_levels,
        latitude=latitude,
        longitude=longitude,
        min_level=min_level,
        max_level=max_level,
        avg_level=avg_level,
        latest_level=latest_level,
        total_records=total_records
    )


# =====================================================
# AUTO STATION UPDATE (AJAX)
# =====================================================

@app.route("/get_stations")
def get_stations():

    district = request.args.get("district")

    if not district:
        return jsonify([])

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT station FROM station_metadata WHERE district=? ORDER BY station",
        (district,)
    )

    stations = [row["station"] for row in cursor.fetchall()]
    conn.close()

    return jsonify(stations)


# =====================================================
# DOWNLOAD CSV
# =====================================================

@app.route("/download")
def download():

    conn = get_connection()
    cursor = conn.cursor()

    selected_station = request.args.get("station")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    if not selected_station:
        return "Please select a station before downloading.", 400

    query = """
        SELECT date, water_level_m
        FROM monthly_data
        WHERE station=?
    """
    params = [selected_station]

    if start_date:
        query += " AND date >= ?"
        params.append(start_date)

    if end_date:
        query += " AND date <= ?"
        params.append(end_date)

    query += " ORDER BY date"

    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return "No data available for selected filters.", 404

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow(["Date", "Water Level (m)"])

    for row in rows:
        writer.writerow([row["date"], row["water_level_m"]])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition":
            f"attachment;filename={selected_station}_groundwater_data.csv"
        }
    )


# =====================================================
# DATA FUNCTIONS FOR AI
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
        FROM daily_data
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

        messages = [{"role": "system", "content": system_prompt}]

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

    except Exception:
        return jsonify({"reply": "AI service temporarily unavailable."})


# =====================================================
# RUN (LOCAL ONLY)
# =====================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)