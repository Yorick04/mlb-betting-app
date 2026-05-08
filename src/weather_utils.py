import requests
from datetime import datetime
from stadiums import STADIUM_COORDS

def get_stadium_weather(team_name, game_time_utc):
    """
    game_time_utc expects the MLB API format: '2026-05-08T23:05:00Z'
    """
    coords = STADIUM_COORDS.get(team_name)
    if not coords: 
        return None

    # We now ask for 'hourly' data and force the timezone to UTC to match MLB
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={coords['lat']}&longitude={coords['lon']}"
        f"&hourly=temperature_2m,relative_humidity_2m,wind_speed_10m"
        f"&temperature_unit=fahrenheit&wind_speed_unit=mph"
        f"&timezone=UTC" 
    )
    
    try:
        response = requests.get(url)
        data = response.json()
        
        # Open-Meteo formats time like "2026-05-08T23:00"
        # MLB formats time like "2026-05-08T23:05:00Z"
        # We slice the MLB time to match the Open-Meteo hourly format
        target_hour = game_time_utc[:14] + "00" 
        
        times = data.get('hourly', {}).get('time', [])
        
        if target_hour in times:
            # Find the index of the hour the game starts
            idx = times.index(target_hour)
        else:
            # If we can't find an exact match, fallback to index 0
            idx = 0

        return {
            "temp": data['hourly']['temperature_2m'][idx],
            "humidity": data['hourly']['relative_humidity_2m'][idx],
            "wind_speed": data['hourly']['wind_speed_10m'][idx],
        }
    except Exception as e:
        print(f"Weather fetch failed for {team_name}: {e}")
        return None