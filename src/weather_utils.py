import requests
from datetime import datetime
from stadiums import STADIUM_COORDS

def get_compass_dir(degrees):
    """Converts wind degrees (0-360) to a readable compass direction."""
    if degrees == "N/A": return "N/A"
    val = int((degrees / 22.5) + .5)
    arr = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
           "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return arr[(val % 16)]

def get_stadium_weather(team_name, game_time_utc):
    coords = STADIUM_COORDS.get(team_name)
    if not coords: 
        return None

    # Added wind_direction_10m to the hourly request
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={coords['lat']}&longitude={coords['lon']}"
        f"&hourly=temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m"
        f"&temperature_unit=fahrenheit&wind_speed_unit=mph"
        f"&timezone=UTC" 
    )
    
    try:
        response = requests.get(url)
        data = response.json()
        
        target_hour = game_time_utc[:14] + "00" 
        times = data.get('hourly', {}).get('time', [])
        
        idx = times.index(target_hour) if target_hour in times else 0

        # Pull the degrees and convert to compass direction
        raw_deg = data['hourly']['wind_direction_10m'][idx]
        compass_dir = get_compass_dir(raw_deg)

        return {
            "temp": data['hourly']['temperature_2m'][idx],
            "humidity": data['hourly']['relative_humidity_2m'][idx],
            "wind_speed": data['hourly']['wind_speed_10m'][idx],
            "wind_dir": compass_dir
        }
    except Exception as e:
        print(f"Weather fetch failed for {team_name}: {e}")
        return None