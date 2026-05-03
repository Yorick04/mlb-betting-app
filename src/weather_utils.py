# -*- coding: utf-8 -*-
"""
Created on Sat May  2 23:32:26 2026

@author: jorda
"""

def get_stadium_weather(team_name):
    api_key = os.getenv("OPENWEATHER_API_KEY")
    coords = STADIUM_COORDS.get(team_name)
    
    if not coords:
        return None

    # Using the current weather endpoint with imperial units (Fahrenheit, MPH)
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={coords['lat']}&lon={coords['lon']}&appid={api_key}&units=imperial"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        return {
            "temp": data['main']['temp'],
            "humidity": data['main']['humidity'],
            "wind_speed": data['wind']['speed'],
            "wind_deg": data['wind']['deg'],  # Direction in degrees (0 is North)
            "conditions": data['weather'][0]['description']
        }
    except Exception as e:
        print(f"Weather error for {team_name}: {e}")
        return None