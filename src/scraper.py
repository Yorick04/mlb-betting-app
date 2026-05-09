import os
from dotenv import load_dotenv
import requests
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import pytz
import time

# Custom utilities
from odds_utils import get_mlb_odds
from weather_utils import get_stadium_weather

load_dotenv(override=True)

def get_google_sheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    env_json = os.getenv("GOOGLE_SHEETS_JSON")
    if not env_json:
        raise ValueError("GOOGLE_SHEETS_JSON not found.")
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
        try:
            sheet.freeze(rows=1)
        except:
            pass

def run_scraper():
    print("--- Starting MLB Scraper (Local Anaconda) ---", flush=True)
    
    try:
        client = get_google_sheet_client()
        sheet = client.open("mlb-betting-app").worksheet("Master")
    except Exception as e:
        print(f"❌ Failed to connect to Google Sheets: {e}")
        return
    
    check_headers(sheet)
    
    today = datetime.now(pytz.timezone('US/Central')).strftime('%Y-%m-%d')

    # 1. Fetch Odds
    odds_data = get_mlb_odds()
    
    # 2. Fetch MLB Schedule
    print("Fetching MLB schedule...", flush=True)
    schedule_url = f"https://statsapi.mlb.com/api/v1/schedule/games/?sportId=1&date={today}&hydrate=probablePitcher"
    
    try:
        response = requests.get(schedule_url, timeout=15).json()
        dates = response.get('dates', [])
        games = dates[0].get('games', []) if dates else []
    except Exception as e:
        print(f"❌ Failed to fetch MLB schedule: {e}", flush=True)
        return

    print(f"Found {len(games)} games. Processing logic...", flush=True)
    
    existing_rows = sheet.get_all_values()
    row_map = {f"{r[0]}_{r[1]}_{r[2]}": i + 1 for i, r in enumerate(existing_rows) if len(r) >= 3}

    games_to_append = []

    for game in games:
        home = game['teams']['home']['team']['name']
        away = game['teams']['away']['team']['name']
        game_time = game.get('gameDate', 'N/A')
        
        hp = game['teams']['home'].get('probablePitcher', {}).get('fullName', 'TBD')
        ap = game['teams']['away'].get('probablePitcher', {}).get('fullName', 'TBD')
        
        print(f"-> Processing: {away} @ {home}", flush=True)
        
        # Weather
        weather = get_stadium_weather(home, game_time)
        if weather:
            temp, wind, wind_dir, hum = weather['temp'], weather['wind_speed'], weather['wind_dir'], weather['humidity']
        else:
            temp, wind, wind_dir, hum = "N/A", "N/A", "N/A", "N/A"

        # Odds Matching (Fuzzy)
        line, ml, book = "N/A", "N/A", "N/A"
        matched_key = None
        
        for key in odds_data.keys():
            if (home in key or home.split()[-1] in key) and (away in key or away.split()[-1] in key):
                matched_key = key
                break
        
        if matched_key:
            line = odds_data[matched_key].get('total', 'N/A')
            ml = odds_data[matched_key].get('ml', 'N/A')
            book = odds_data[matched_key].get('book', 'DraftKings')
        else:
            print(f"   ⚠️ No Odds match found for {away} @ {home}", flush=True)

        # Alert Logic
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

        time.sleep(2)

    if games_to_append:
        sheet.append_rows(games_to_append, value_input_option="USER_ENTERED")
        print(f"✅ Success: Appended {len(games_to_append)} new games.", flush=True)
    else:
        print("✅ Success: Master Sheet updated.", flush=True)

if __name__ == "__main__":
    run_scraper()