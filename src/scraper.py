import os
from dotenv import load_dotenv
import requests
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import pytz

# Import your custom utility files
from odds_utils import get_mlb_odds
from weather_utils import get_stadium_weather

# Load local environment variables (does nothing if running in GitHub Actions)
load_dotenv(override=True)

def get_google_sheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    env_json = os.getenv("GOOGLE_SHEETS_JSON")
    creds_info = json.loads(env_json)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
    return gspread.authorize(creds)

def check_headers(sheet):
    """Ensures the Master sheet has headers and formatting if empty."""
    first_row = sheet.row_values(1)
    
    # Updated to 15 columns (Added 'Wind Dir')
    headers = [
        "Date/Time (CT)", "Home", "Away", "Home Pitcher", "Away Pitcher", 
        "Bookmaker", "ML Odds", "O/U Total", "Temp", "Wind", "Wind Dir", 
        "Humidity", "Value Alert", "Actual Total", "Result"
    ]
    
    if not first_row or first_row[0] == "":
        print("Headers missing. Rebuilding...")
        sheet.insert_row(headers, 1)
        # Bold headers A through O
        sheet.format("A1:O1", {"textFormat": {"bold": True}})
        sheet.update_title("Master")
        try:
            sheet.freeze(rows=1)
        except:
            pass

def run_scraper():
    print("--- Starting MLB Scrape with Upsert & Directional Wind ---")
    
    client = get_google_sheet_client()
    sheet = client.open("mlb-betting-app").worksheet("Master")
    
    check_headers(sheet)
    
    today = datetime.now(pytz.timezone('US/Central')).strftime('%Y-%m-%d')

    print("Fetching odds and schedule...")
    odds_data = get_mlb_odds()
    
    schedule_url = f"https://statsapi.mlb.com/api/v1/schedule/games/?sportId=1&date={today}&hydrate=probablePitcher"
    games = requests.get(schedule_url).json().get('dates', [{}])[0].get('games', [])

    # --- UPSERT LOGIC SETUP ---
    existing_rows = sheet.get_all_values()
    row_map = {}
    
    # Map out the rows that already exist today
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
        
        hp = game['teams']['home'].get('probablePitcher', {}).get('fullName', 'TBD')
        ap = game['teams']['away'].get('probablePitcher', {}).get('fullName', 'TBD')
        
        # 1. Weather Hook (Open-Meteo with game time and wind direction)
        weather = get_stadium_weather(home, game_time)
        if weather:
            temp = weather['temp']
            wind = weather['wind_speed']
            wind_dir = weather['wind_dir']
            hum = weather['humidity']
        else:
            temp, wind, wind_dir, hum = "N/A", "N/A", "N/A", "N/A"

        # 2. Odds Hook (DraftKings filtered)
        game_key_odds = f"{home}_{away}"
        if game_key_odds in odds_data:
            line = odds_data[game_key_odds].get('total', 'N/A')
            ml = odds_data[game_key_odds].get('ml', 'N/A')
            book = odds_data[game_key_odds].get('book', 'Unknown')
        else:
            line, ml, book = "N/A", "N/A", "N/A"
        
        # 3. Smart Alert Logic
        alert = ""
        if temp != "N/A" and float(temp) > 85: 
            alert = "🔥 OVER (Heat)"
        if wind != "N/A" and float(wind) > 12: 
            alert = f"💨 WINDY ({wind_dir})"

        # 4. Prepare row data (15 columns to match the new headers)
        row_data = [today, home, away, hp, ap, book, ml, line, temp, wind, wind_dir, hum, alert, "", ""]
        
        # --- UPSERT EXECUTION ---
        game_key_sheet = f"{today}_{home}_{away}"
        
        if game_key_sheet in row_map:
            # Game exists! Update columns A through M (13 columns)
            # This leaves Columns N (Actual) and O (Result) untouched if they have data
            row_num = row_map[game_key_sheet]
            sheet.update(range_name=f"A{row_num}:M{row_num}", values=[row_data[:13]])
            print(f"🔄 Updated existing game: {away} @ {home}")
        else:
            # Game is new!
            games_to_append.append(row_data)
            print(f"➕ New game found: {away} @ {home}")

    if games_to_append:
        sheet.append_rows(games_to_append, value_input_option="USER_ENTERED")
        print(f"Appended {len(games_to_append)} new games to Master.")
    else:
        print("No new games to append. All existing games updated.")

if __name__ == "__main__":
    run_scraper()