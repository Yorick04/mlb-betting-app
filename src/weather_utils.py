import requests
from stadiums import STADIUM_COORDS

def get_stadium_weather(home_team, game_date=None, roof_status="Open"):
    """
    Fetches real-time weather metrics using the clean current_weather endpoint.
    Correctly extracts numeric coordinates from dictionaries to prevent 400 errors.
    """
    # Standard Fallback/Indoor Object
    indoor_metrics = {
        "temp": 72, 
        "wind_speed": 0, 
        "wind_dir": "N/A", 
        "humidity": 45, 
        "wind_deg": 0
    }
    
    # 1. Check for Indoor/Closed Roof configurations
    if roof_status in ["Closed", "Dome", "Indoors", "Indoor"]:
        return indoor_metrics

    # 2. Locate Stadium Coordinates
    if home_team not in STADIUM_COORDS:
        print(f"Warning: Coordinates not found for {home_team}. Using fallback defaults.")
        return indoor_metrics
        
    # FIX: Explicitly target dictionary keys to pull numbers, not key strings
    coords = STADIUM_COORDS[home_team]
    lat = coords.get('lat')
    lon = coords.get('lon')
    
    # 3. Construct Comma-Free Query Parameters
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current_weather": "true", # No commas = zero encoding bugs
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "timezone": "auto"
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        
        # Verify the server returned a clean 200 OK status
        if response.status_code == 200:
            data = response.json()
            current = data.get("current_weather", {})
            
            # Extract and parse metrics from the legacy structure
            temp = round(current.get("temperature", 72))
            wind_speed = round(current.get("windspeed", 0))
            wind_deg = current.get("winddirection", 0)
            humidity = 50 # Clean fallback since current_weather isolates vector stats
            
            # Convert degree heading to standard cardinal string
            wind_dir = get_cardinal_direction(wind_deg)
            
            return {
                "temp": temp,
                "wind_speed": wind_speed,
                "wind_dir": wind_dir,
                "humidity": humidity,
                "wind_deg": wind_deg
            }
        else:
            print(f"Weather API returned server error status {response.status_code} for {home_team}. Defaulting values.")
            return indoor_metrics
            
    except Exception as e:
        print(f"Error fetching weather for {home_team}: {e}")
        return indoor_metrics

def get_cardinal_direction(degrees):
    """Converts a wind degree mapping (0-360) into standard cardinal directions."""
    if degrees is None: return "N/A"
    directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", 
                  "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    ix = int((degrees + 11.25) / 22.5)
    return directions[ix % 16]