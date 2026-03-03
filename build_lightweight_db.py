import pandas as pd
import sqlite3

# Load compressed pickle
df = pd.read_pickle("data/groundwater.pkl", compression="gzip")

# Keep only needed columns
df = df[["district", "station", "latitude", "longitude", "date", "water_level_m"]]

df["date"] = pd.to_datetime(df["date"])

# ======================================
# 1️⃣ DAILY Aggregation (Instead of Monthly)
# ======================================

daily = (
    df.set_index("date")
      .groupby(["district", "station", "latitude", "longitude"])
      .resample("D")["water_level_m"]
      .mean()
      .reset_index()
)

# ======================================
# 2️⃣ Latest Reading Per Station
# ======================================

latest = (
    df.sort_values("date")
      .groupby(["district", "station"])
      .tail(1)
      .reset_index(drop=True)
)

# ======================================
# 3️⃣ Station Metadata Table
# ======================================

station_metadata = df[["district", "station", "latitude", "longitude"]].drop_duplicates()

# ======================================
# 4️⃣ Save to SQLite
# ======================================

conn = sqlite3.connect("data/groundwater_light.db")

daily.to_sql("daily_data", conn, if_exists="replace", index=False)
latest.to_sql("latest_data", conn, if_exists="replace", index=False)
station_metadata.to_sql("station_metadata", conn, if_exists="replace", index=False)

conn.close()

print("Lightweight DAILY DB created successfully.")