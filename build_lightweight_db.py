import pandas as pd
import sqlite3

df = pd.read_pickle("data/groundwater.pkl", compression="gzip")

df = df[["district", "station", "date", "water_level_m", "latitude", "longitude"]]
df["date"] = pd.to_datetime(df["date"])

# Monthly aggregation
monthly = (
    df.set_index("date")
      .groupby(["district", "station", "latitude", "longitude"])
      .resample("ME")["water_level_m"]
      .mean()
      .reset_index()
)

# Latest reading
latest = (
    df.sort_values("date")
      .groupby(["district", "station"])
      .tail(1)
      .reset_index(drop=True)
)

# Station metadata (unique)
stations = df[["district", "station", "latitude", "longitude"]].drop_duplicates()

conn = sqlite3.connect("data/groundwater_light.db")

monthly.to_sql("monthly_data", conn, if_exists="replace", index=False)
latest.to_sql("latest_data", conn, if_exists="replace", index=False)
stations.to_sql("station_metadata", conn, if_exists="replace", index=False)

conn.close()

print("Lightweight DB with coordinates created.")