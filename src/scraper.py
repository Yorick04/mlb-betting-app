import os
import json
import pandas as pd
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
from datetime import datetime
import pytz

# Local Imports
from odds_utils import get_mlb_odds
from weather_utils import get_stadium_weather

# Load environment variables
load_dotenv(override=True)

def get_google_sheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    env_json = os.getenv("GOOGLE_SHEETS_JSON")
    if env_json:
        creds_info = json.loads(env_json)
        return gspread.authorize(ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope))
    return gspread.authorize(ServiceAccountCredentials.from_json_keyfile_name('service_account_key.json', scope))

def get_mlb_daily_schedule(date_str):
    url = f"https://statsapi.mlb.com/api/v1/schedule/games/?sportId=1&date={date_str}&hydrate=probablePitcher"
    try:
        response = requests.get(url).json()
        games = []
        if "dates" in response and response["dates"]:
            for game in response["dates"][0]["games"]:
                home_p = game['teams']['home'].get('probablePitcher', {}).get('fullName', 'TBA')
                away_p = game['teams']['away'].get('probablePitcher', {}).get('fullName', 'TBA')
                games.append({
                    'game_utc': game['gameDate'],
                    'home_name': game['teams']['home']['team']['name'],
                    'away_name': game['teams']['away']['team']['name'],
                    'home_pitcher': home_p,
                    'away_pitcher': away_p
                })
        return pd.DataFrame(games)
    except Exception as e:
        print(f"Error fetching MLB schedule: {e}")
        return pd.DataFrame()

def run_scraper():
    today = datetime.now().strftime('%Y-%m-%d')
    print(f"--- Starting Pipeline for {today} ---")

    schedule = get_mlb_daily_schedule(today)
    if schedule.empty:
        print("No games scheduled.")
        return

    odds_data = get_mlb_odds()
    
    try:
        client = get_google_sheet_client()
        sheet = client.open("mlb-betting-app").sheet1
        sheet.clear()
    except Exception as e:
        print(f"Sheets Error: {e}")
        return

    final_data = []
    # Added "Bookmaker" to the headers
    headers = ["Date/Time (CT)", "Home", "Away", "Home Pitcher", "Away Pitcher", "Bookmaker", "ML Odds", "O/U Total", "Temp", "Wind", "Humidity", "Value Alert"]

    for _, row in schedule.iterrows():
        # Time conversion
        utc_dt = datetime.strptime(row['game_utc'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.utc)
        local_dt = utc_dt.astimezone(pytz.timezone("US/Central"))
        game_time_str = local_dt.strftime("%m/%d %I:%M %p")

        home_team = row['home_name']
        away_team = row['away_name']
        
        weather = get_stadium_weather(home_team)
        if weather:
            temp_val, wind_val = weather["temp"], weather["wind_speed"]
            w_txt, wind_txt, hum_txt = f"{temp_val}°F", f"{wind_val} MPH @ {weather['wind_deg']}°", f"{weather['humidity']}%"
        else:
            w_txt, wind_txt, hum_txt, temp_val, wind_val = "N/A", "N/A", "N/A", None, None

        # Fetch odds and book name
        lookup_key = f"{home_team}_{away_team}"
        game_odds = odds_data.get(lookup_key, {"ml": "N/A", "total": "N/A", "book": "N/A"})
        
        alert = "None"
        if temp_val and game_odds['total'] != "N/A":
            if temp_val > 85 and float(game_odds['total']) <= 8.5:
                alert = "🔥 OVER (Heat)"
            elif wind_val and wind_val > 12:
                alert = "💨 WIND ALERT"

        final_data.append([
            game_time_str, home_team, away_team, row['home_pitcher'], row['away_pitcher'],
            game_odds.get('book', 'N/A'), # New Bookmaker column
            game_odds['ml'], game_odds['total'], w_txt, wind_txt, hum_txt, alert
        ])

    sheet.update(values=[headers] + final_data, range_name='A1')
    print(f"Success! {len(final_data)} games pushed with Bookmaker info.")

if __name__ == "__main__":
    run_scraper()