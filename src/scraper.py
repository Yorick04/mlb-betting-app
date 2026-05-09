import os
from dotenv import load_dotenv
import requests
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import pytz

from odds_utils import get_mlb_odds
from weather_utils import get_stadium_weather

load_dotenv(override=True)

def get_google_sheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    env_json = os.getenv("GOOGLE_SHEETS_JSON")
    creds_info = json.loads(env_json)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
    return gspread.authorize(creds)

def check_headers(sheet):
    first_row = sheet.row_values(1)
    headers = [
        "Date/Time (CT)", "Home", "Away", "Home Pitcher", "Away Pitcher", 
        "Bookmaker", "ML Odds", "O/U Total", "Temp", "Wind", "Wind Dir", 
        "Humidity", "Value Alert", "Actual Total", "Result"
    ]
    if not first_row or first_row[0] == "":
        print("Headers missing. Rebuilding...", flush=True)
        sheet.insert_row(headers, 1)
        sheet.format("A1:O1", {"textFormat": {"bold": True}})
        sheet.update_title("Master")
        try:
            sheet.freeze(rows=1)
        except:
            pass

def run_scraper():
    # flush=True forces GitHub to show us the text IMMEDIATELY
    print("--- Starting MLB Scrape with Upsert & Directional Wind ---", flush=True)
    
    client = get_google_sheet_client()
    sheet = client.open("mlb-betting-app").worksheet("Master")
    
    check_headers(sheet)
    
    today = datetime.now(pytz.timezone('US/Central')).strftime('%Y-%m-%d')

    print("Fetching odds data...", flush=True)
    odds_data = get_mlb_odds()
    
    print("Fetching MLB schedule...", flush=True)
    schedule_url = f"https://statsapi.mlb.com/api/v1/schedule/games/?sportId=1&date={today}&hydrate=probablePitcher"
    
    try:
        # Added a 10 second timeout so we never freeze again
        response = requests.get(schedule_url, timeout=10).json()
        dates = response.get('dates', [])
        games = dates[0].get('games', []) if dates else []
    except Exception as e:
        print(f"Failed to fetch MLB schedule: {e}", flush=True)
        games = []

    if not games:
        print("No games found for today or MLB API failed.", flush=True)
        return

    print(f"Found {len(games)} games. Checking existing rows in sheet...", flush=True)
    existing_rows = sheet.get_all_values()
    row_map = {}
    
    for i, row in enumerate(existing_rows):
        if i == 0: continue 
        if len(row) >= 3:
            key = f"{row[0]}_{row[1]}_{row[2]}"
            row_map[key] = i + 1 

    games_to_append = []

    for game in games:
        home = game['teams']['home']['team']['name']
        away = game['teams']['away']['team']['name']
        game_time = game.get('gameDate', 'N/A')
        
        print(f"Processing: {away} @ {home}...", flush=True)
        
        hp = game['teams']['home'].get('probablePitcher', {}).get('fullName', 'TBD')
        ap = game['teams']['away'].get('probablePitcher', {}).get('fullName', 'TBD')
        
        weather = get_stadium_weather(home, game_time)
        if weather:
            temp, wind, wind_dir, hum = weather['temp'], weather['wind_speed'], weather['wind_dir'], weather['humidity']
        else:
            temp, wind, wind_dir, hum = "N/A", "N/A", "N/A", "N/A"

        game_key_odds = f"{home}_{away}"
        if game_key_odds in odds_data:
            line, ml, book = odds_data[game_key_odds].get('total', 'N/A'), odds_data[game_key_odds].get('ml', 'N/A'), odds_data[game_key_odds].get('book', 'Unknown')
        else:
            line, ml, book = "N/A", "N/A", "N/A"
        
        alert = ""
        if temp != "N/A" and float(temp) > 85: alert = "🔥 OVER (Heat)"
        if wind != "N/A" and float(wind) > 12: alert = f"💨 WINDY ({wind_dir})"

        row_data = [today, home, away, hp, ap, book, ml, line, temp, wind, wind_dir, hum, alert, "", ""]
        game_key_sheet = f"{today}_{home}_{away}"
        
        if game_key_sheet in row_map:
            row_num = row_map[game_key_sheet]
            sheet.update(range_name=f"A{row_num}:M{row_num}", values=[row_data[:13]])
        else:
            games_to_append.append(row_data)

    if games_to_append:
        print(f"Appending {len(games_to_append)} new games to Sheet...", flush=True)
        sheet.append_rows(games_to_append, value_input_option="USER_ENTERED")
        print("Append complete!", flush=True)
    else:
        print("No new games to append. All existing games updated.", flush=True)

if __name__ == "__main__":
    run_scraper()