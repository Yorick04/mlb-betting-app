import os
import json
import gspread
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials

# --- The Permanent Fix for Module Pathing ---
try:
    # This works when running from the project root (like GitHub Actions)
    from src.stadiums import STADIUM_COORDS
except ModuleNotFoundError:
    # This works when running directly from the /src folder (like your local PC)
    from stadiums import STADIUM_COORDS

load_dotenv()

def get_google_sheet_client():
    """Authenticates with Google Sheets using local file or GitHub Secret."""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # Check for GitHub Secret environment variable first
    if "GOOGLE_SHEETS_JSON" in os.environ:
        creds_info = json.loads(os.environ["GOOGLE_SHEETS_JSON"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
    else:
        # Fallback to local service account file for manual testing
        current_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(current_dir)
        key_path = os.path.join(parent_dir, 'service_account_key.json')
        creds = ServiceAccountCredentials.from_json_keyfile_name(key_path, scope)
        
    return gspread.authorize(creds)

def get_weather(team_name):
    """Fetches real-time weather from OpenWeather for the home stadium."""
    api_key = os.getenv("OPENWEATHER_API_KEY")
    coords = STADIUM_COORDS.get(team_name)
    
    if not coords or not api_key:
        return {"temp": "N/A", "wind": "N/A", "humidity": "N/A"}
    
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={coords['lat']}&lon={coords['lon']}&appid={api_key}&units=imperial"
    
    try:
        response = requests.get(url)
        data = response.json()
        return {
            "temp": f"{round(data['main']['temp'])}°F",
            "wind": f"{data['wind']['speed']} MPH @ {data['wind'].get('deg', 0)}°",
            "humidity": f"{data['main']['humidity']}%"
        }
    except Exception:
        return {"temp": "Error", "wind": "Error", "humidity": "Error"}

def run_daily_update():
    """Main execution: Scrapes MLB slate, merges weather, and updates Google Sheets."""
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"--- Fetching MLB Slate & Weather for {today} ---")
    
    # 1. Fetch MLB Schedule from StatsAPI
    mlb_url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={today}&hydrate=probablePitcher"
    try:
        data = requests.get(mlb_url).json()
    except Exception as e:
        print(f"MLB API Error: {e}")
        return

    games = []
    if 'dates' in data and len(data['dates']) > 0:
        for game in data['dates'][0]['games']:
            home_team = game['teams']['home']['team']['name']
            weather = get_weather(home_team) # Integrated weather fetch
            
            games.append({
                'Home': home_team,
                'Away': game['teams']['away']['team']['name'],
                'Home Pitcher': game['teams']['home'].get('probablePitcher', {}).get('fullName', 'TBA'),
                'Away Pitcher': game['teams']['away'].get('probablePitcher', {}).get('fullName', 'TBA'),
                'Temp': weather['temp'],
                'Wind': weather['wind'],
                'Humidity': weather['humidity']
            })

    if not games:
        print("No games scheduled for today.")
        return

    # 2. Process and Upload
    try:
        df = pd.DataFrame(games)
        client = get_google_sheet_client()
        spreadsheet = client.open("mlb-betting-app")
        worksheet = spreadsheet.get_worksheet(0)

        # Clear and update with the latest data
        worksheet.clear()
        data_to_upload = [df.columns.values.tolist()] + df.values.tolist()
        worksheet.update(values=data_to_upload, range_name='A1')
        
        print(f"Success! {len(df)} games pushed to 'mlb-betting-app'.")
    except Exception as e:
        print(f"Update Error: {e}")

if __name__ == "__main__":
    run_daily_update()