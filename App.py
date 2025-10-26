# app.py
import os
import requests
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta, timezone
import streamlit as st
from dotenv import load_dotenv

# Load .env if present
load_dotenv()

API_KEY = "5dca0cbaba07a83d089df84b8751d7a3"
if not API_KEY:
    st.error("OpenWeatherMap API key not found. Set OPENWEATHER_API_KEY environment variable.")
    st.stop()

# --- Helper functions ---
@st.cache_data(ttl=300)
def fetch_current_weather(city: str, units: str = "metric"):
    """Fetch current weather from OpenWeatherMap."""
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"q": city, "appid": API_KEY, "units": units}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=300)
def fetch_forecast(city: str, units: str = "metric"):
    """Fetch 5-day / 3-hour forecast."""
    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {"q": city, "appid": API_KEY, "units": units}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    return r.json()

def format_time_from_unix(ts, tz_offset_seconds):
    # OpenWeather returns UTC unix timestamp, and timezone offset (in seconds) for the location
    tz = timezone(timedelta(seconds=tz_offset_seconds))
    return datetime.fromtimestamp(ts, tz=tz).strftime("%Y-%m-%d %H:%M")

def icon_url(icon_code):
    # OpenWeatherMap icon URL (dynamic icons)
    return f"http://openweathermap.org/img/wn/{icon_code}@2x.png"

def build_daily_summary(forecast_json):
    """Aggregate 3-hourly forecast into daily high/low & mean temperature."""
    items = forecast_json.get("list", [])
    rows = []
    for it in items:
        dt = datetime.utcfromtimestamp(it["dt"])  # will adjust for tz later if necessary
        rows.append({
            "dt": dt,
            "temp": it["main"]["temp"],
            "temp_min": it["main"]["temp_min"],
            "temp_max": it["main"]["temp_max"],
            "weather_main": it["weather"][0]["main"],
            "weather_desc": it["weather"][0]["description"],
            "icon": it["weather"][0]["icon"],
        })
    df = pd.DataFrame(rows)
    df["date"] = df["dt"].dt.date
    daily = df.groupby("date").agg({
        "temp": "mean",
        "temp_min": "min",
        "temp_max": "max",
        "icon": lambda icons: icons.iloc[len(icons)//2]  # pick middle icon as representative
    }).reset_index()
    return daily

# --- Streamlit UI ---
st.set_page_config(page_title="Real-Time Weather", layout="wide")
st.title("🌤 Real-Time Weather App (OpenWeatherMap + Streamlit)")

# Inputs: city and units
with st.sidebar:
    st.header("Controls")
    city = st.text_input("Enter city (city, country optional)", value="Mumbai,IN")
    unit_option = st.selectbox("Units", options=["Celsius (°C)", "Fahrenheit (°F)"])
    units = "metric" if "Celsius" in unit_option else "imperial"
    show_details = st.checkbox("Show raw JSON responses (debug)", value=False)
    st.caption("Data from OpenWeatherMap (current + 5-day forecast)")

if not city or city.strip() == "":
    st.warning("Please enter a city name.")
    st.stop()

# Fetch data
try:
    with st.spinner("Fetching weather data..."):
        current = fetch_current_weather(city, units=units)
        forecast = fetch_forecast(city, units=units)
except requests.HTTPError as e:
    st.error(f"API request failed: {e}")
    st.stop()
except Exception as e:
    st.error(f"Unexpected error: {e}")
    st.stop()

if show_details:
    st.subheader("Raw Current Weather JSON")
    st.json(current)
    st.subheader("Raw Forecast JSON")
    st.json(forecast)

# Parse current weather
name = f"{current.get('name', '')}, {current.get('sys', {}).get('country','')}"
weather = current["weather"][0]
main = current["main"]
wind = current.get("wind", {})
visibility = current.get("visibility", None)
tz_offset = current.get("timezone", 0)  # seconds offset from UTC
sunrise = current["sys"].get("sunrise")
sunset = current["sys"].get("sunset")

col1, col2 = st.columns([2, 3])
with col1:
    st.subheader(f"{name}")
    st.markdown(f"**{weather['main']} — {weather['description'].capitalize()}**")
    # Show icon
    st.image(icon_url(weather["icon"]), width=100)
    st.metric(label="Temperature", value=f"{main['temp']}° {'C' if units=='metric' else 'F'}",
              delta=f"{main.get('feels_like', '?') - main.get('temp',0):+.1f}")
    st.markdown(f"- **Humidity:** {main.get('humidity', '?')}%")
    st.markdown(f"- **Pressure:** {main.get('pressure', '?')} hPa")
    st.markdown(f"- **Wind speed:** {wind.get('speed', '?')} {'m/s' if units=='metric' else 'mph'}")
    if visibility is not None:
        st.markdown(f"- **Visibility:** {visibility} m")
    st.markdown(f"- **Sunrise:** {format_time_from_unix(sunrise, tz_offset)}")
    st.markdown(f"- **Sunset:** {format_time_from_unix(sunset, tz_offset)}")

with col2:
    st.subheader("5-Day Forecast")
    daily = build_daily_summary(forecast)
    # Convert date to string for display
    daily["date_str"] = daily["date"].astype(str)
    st.write("Daily summary (mean temp, min, max):")
    st.dataframe(daily[["date_str", "temp", "temp_min", "temp_max"]].rename(columns={
        "date_str":"Date", "temp":"Mean Temp", "temp_min":"Min Temp", "temp_max":"Max Temp"
    }), use_container_width=True)

    # Plot daily mean + min/max as lines and filled area
    fig, ax = plt.subplots(figsize=(8,3))
    ax.plot(daily["date_str"], daily["temp"], marker="o", label="Mean")
    ax.plot(daily["date_str"], daily["temp_max"], linestyle="--", marker="^", label="Max")
    ax.plot(daily["date_str"], daily["temp_min"], linestyle="--", marker="v", label="Min")
    ax.fill_between(daily["date_str"], daily["temp_min"], daily["temp_max"], alpha=0.1)
    ax.set_xlabel("Date")
    ax.set_ylabel(f"Temperature (°{'C' if units=='metric' else 'F'})")
    ax.set_title("5-day Forecast (daily min/mean/max)")
    ax.grid(alpha=0.2)
    ax.legend()
    plt.xticks(rotation=15)
    st.pyplot(fig)

# Show hourly 3-hourly forecast (optional)
st.subheader("3-hourly Forecast (next 5 days)")
fc_list = forecast.get("list", [])
rows = []
for it in fc_list:
    dt_local = datetime.utcfromtimestamp(it["dt"]) + timedelta(seconds=tz_offset)  # adjust to location tz
    rows.append({
        "datetime": dt_local.strftime("%Y-%m-%d %H:%M"),
        "temp": it["main"]["temp"],
        "temp_min": it["main"]["temp_min"],
        "temp_max": it["main"]["temp_max"],
        "weather": it["weather"][0]["description"],
        "icon": it["weather"][0]["icon"]
    })
hourly_df = pd.DataFrame(rows)
# show first 12 rows to avoid long output
st.dataframe(hourly_df.head(12), use_container_width=True)

# Small legend with icons for the next 5 days
st.subheader("Representative icons for upcoming days")
icon_cols = st.columns(len(daily))
for i, (_, row) in enumerate(daily.iterrows()):
    with icon_cols[i]:
        st.image(icon_url(row["icon"]), width=80)
        st.caption(str(row["date"]))

st.markdown("---")
st.info("Tip: if you get 'city not found', try: `CityName,countryCode` (e.g. `London,GB` or `Mumbai,IN`).")

# Sample queries
st.subheader("Sample queries to try")
st.write("""
- `New York,US`  
- `Mumbai,IN`  
- `Tokyo,JP`  
- `London,GB`  
- `Sydney,AU`
""")
