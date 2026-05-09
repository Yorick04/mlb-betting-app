import requests
from stadiums import STADIUM_COORDS

# List of stadiums that are domes or have retractable roofs
RETRACTABLE = ["Arizona Diamondbacks", "Texas Rangers", "Seattle Mariners", "Milwaukee Brewers", "Houston Astros", "Miami Marlins"]
PERMANENT_DOMES = ["Toronto Blue Jays", "Tampa Bay Rays"]

def get_compass_dir(degrees):
    if degrees == "N/A" or degrees is None: return "N/A"
    arr = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return arr[(int((degrees / 22.5) + .5) % 16)]

def get_stadium_weather(team_name, game_time_utc, roof_status="Open"):
    # If it's a permanent dome, or a retractable roof that is NOT open, return indoor constants
    if team_name in PERMANENT_DOMES or (team_name in RETRACTABLE and "Open" not in str(roof_status)):
        return {"temp": 72.0, "humidity": 45, "wind_speed": 0.0, "wind_dir": "INDOORS", "wind_deg": 0}
    
    coords = STADIUM_COORDS.get(team_name)
    if not coords: return None
    
    url = f"https://api.open-meteo.com/v1/forecast?latitude={coords['lat']}&longitude={coords['lon']}&hourly=temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m&temperature_unit=fahrenheit&wind_speed_unit=mph&timezone=UTC"
    
    try:
        response = requests.get(url, timeout=10).json()
        target_hour = game_time_utc[:14] + "00"
        times = response.get('hourly', {}).get('time', [])
        idx = times.index(target_hour) if target_hour in times else 0
        raw_deg = response['hourly']['wind_direction_10m'][idx]
        
        return {
            "temp": response['hourly']['temperature_2m'][idx],
            "humidity": response['hourly']['relative_humidity_2m'][idx],
            "wind_speed": response['hourly']['wind_speed_10m'][idx],
            "wind_dir": get_compass_dir(raw_deg),
            "wind_deg": raw_deg
        }
    except: return None