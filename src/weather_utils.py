import os
import requests
from stadiums import STADIUM_COORDS

def get_stadium_weather(team_name):
    api_key = os.getenv("OPENWEATHER_API_KEY")
    coords = STADIUM_COORDS.get(team_name)
    if not coords: return None

    url = f"https://api.openweathermap.org/data/2.5/weather?lat={coords['lat']}&lon={coords['lon']}&appid={api_key}&units=imperial"
    try:
        data = requests.get(url).json()
        return {
            "temp": data['main']['temp'],
            "humidity": data['main']['humidity'],
            "wind_speed": data['wind']['speed'],
            "wind_deg": data['wind']['deg'],
            "conditions": data['weather'][0]['description']
        }
    except:
        return None