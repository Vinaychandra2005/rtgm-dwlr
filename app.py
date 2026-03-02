from flask import Flask, render_template, request, send_file, jsonify
import pandas as pd
import numpy as np
import requests
import os
import logging
import matplotlib.pyplot as plt

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch

# =====================================================
# 🔐 CONFIGURATION
# =====================================================

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

logging.basicConfig(level=logging.WARNING)

app = Flask(__name__)

# =====================================================
# 📂 LOAD DATASET (OPTIMIZED PICKLE)
# =====================================================

df = pd.read_pickle("data/groundwater.pkl", compression="gzip")

# Memory optimization for large dataset
df["district"] = df["district"].astype("category")
df["station"] = df["station"].astype("category")

print("Dataset Loaded | Records:", len(df))

# =====================================================
# 📈 ANALYTICS FUNCTIONS
# =====================================================

def detect_station(user_message):
    message_lower = user_message.lower()

    for station in df["station"].unique():
        if station.lower() in message_lower:
            return station

    message_clean = message_lower.replace("_", "").replace(" ", "")
    for station in df["station"].unique():
        station_clean = station.lower().replace("_", "").replace(" ", "")
        if station_clean in message_clean:
            return station

    return None


def compute_station_trend(user_message):
    station = detect_station(user_message)
    if not station:
        return None

    filtered = df[df["station"] == station]

    monthly = (
        filtered
        .set_index("date")
        .resample("ME")["water_level_m"]
        .mean()
        .dropna()
    )

    if len(monthly) < 2:
        return None

    x = monthly.index.year + (monthly.index.month - 1) / 12.0
    y = monthly.values

    slope, _ = np.polyfit(x, y, 1)

    if slope > 0:
        trend = "Rising"
    elif slope < 0:
        trend = "Declining"
    else:
        trend = "Stable"

    return f"""
    Station: {station}
    Trend Classification: {trend}
    Trend Slope: {slope:.3f} meters per year
    Time Period: {monthly.index.min().date()} to {monthly.index.max().date()}
    """


def get_latest_reading(user_message):
    station = detect_station(user_message)
    if not station:
        return None

    filtered = df[df["station"] == station].sort_values("date")
    if filtered.empty:
        return None

    latest_row = filtered.iloc[-1]

    return f"""
    Station: {station}
    Latest Water Level: {latest_row['water_level_m']:.2f} meters
    Timestamp: {latest_row['date']}
    """


def get_stations_by_district(user_message):
    message_lower = user_message.lower()

    for district in df["district"].unique():
        if district.lower() in message_lower:
            stations = df[df["district"] == district]["station"].unique()
            station_list = ", ".join(sorted(stations))
            return f"""
            District: {district}
            Total Stations: {len(stations)}
            Stations: {station_list}
            """

    return None


# =====================================================
# 🏠 ROUTES
# =====================================================

@app.route("/")
def logo_page():
    return render_template("logo.html")

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

@app.route("/monitoring")
def monitoring_page():
    return render_template("monitoring.html")

@app.route("/support")
def support_page():
    return render_template("support.html")


# =====================================================
# 🤖 AI CHAT ROUTE
# =====================================================

@app.route("/chat", methods=["POST"])
def chat():
    try:
        user_message = request.json.get("message")

        if not user_message:
            return jsonify({"reply": "Please enter a question."})

        system_prompt = """
        You are an AI assistant for the RTGM DWLR system.
        You have access to computed dataset results provided in system messages.
        Always use provided data.
        Never say you do not have dataset access.
        Do not fabricate numbers.
        Be technical and scientific.
        """

        latest_context = None
        trend_context = None
        district_context = None

        if "latest" in user_message.lower():
            latest_context = get_latest_reading(user_message)
        elif "trend" in user_message.lower():
            trend_context = compute_station_trend(user_message)
        else:
            district_context = get_stations_by_district(user_message)

        messages = [{"role": "system", "content": system_prompt}]

        if latest_context:
            messages.append({"role": "system", "content": latest_context})

        if trend_context:
            messages.append({"role": "system", "content": trend_context})

        if district_context:
            messages.append({"role": "system", "content": district_context})

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
            }
        )

        if response.status_code != 200:
            return jsonify({"reply": "AI API error."})

        result = response.json()

        if "choices" not in result:
            return jsonify({"reply": "Unexpected AI response."})

        reply = result["choices"][0]["message"]["content"]

        return jsonify({"reply": reply})

    except Exception as e:
        logging.error(f"AI ERROR: {e}")
        return jsonify({"reply": "AI service temporarily unavailable."})


# =====================================================
# 🚀 RUN
# =====================================================

if __name__ == "__main__":
    app.run()