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
        "Bookmaker", "ML Odds", "O/U Total", "Temp", "Wind", 
        "Humidity", "Value Alert", "Actual Total", "Result"
    ]
    if not first_row or first_row[0] == "":
        print("Headers missing. Rebuilding...")
        sheet.insert_row(headers, 1)
        sheet.format("A1:N1", {"textFormat": {"bold": True}})
        sheet.update_title("Master")

def run_scraper():
    print("--- Starting MLB Scrape with Upsert Logic ---")
    
    client = get_google_sheet_client()
    sheet = client.open("mlb-betting-app").worksheet("Master")
    check_headers(sheet)
    
    today = datetime.now(pytz.timezone('US/Central')).strftime('%Y-%m-%d')

    print("Fetching odds and schedule...")
    odds_data = get_mlb_odds()
    
    schedule_url = f"https://statsapi.mlb.com/api/v1/schedule/games/?sportId=1&date={today}&hydrate=probablePitcher"
    games = requests.get(schedule_url).json().get('dates', [{}])[0].get('games', [])

    # --- UPSERT LOGIC SETUP ---
    # 1. Get all current rows to map existing games
    existing_rows = sheet.get_all_values()
    row_map = {}
    
    # Start loop at 1 to skip headers. Add 1 to index because Sheets are 1-indexed.
    for i, row in enumerate(existing_rows):
        if i == 0: continue 
        # Create a unique key: Date_Home_Away
        if len(row) >= 3:
            key = f"{row[0]}_{row[1]}_{row[2]}"
            row_map[key] = i + 1 

    games_to_append = []

    for game in games:
        home = game['teams']['home']['team']['name']
        away = game['teams']['away']['team']['name']
        
  # 1. Grab the official game time from the MLB API
        game_time = game.get('gameDate', 'N/A')
        
        hp = game['teams']['home'].get('probablePitcher', {}).get('fullName', 'TBD')
        ap = game['teams']['away'].get('probablePitcher', {}).get('fullName', 'TBD')
        
        weather = get_stadium_weather(home, game_time)
        if weather:
            temp = weather['temp']
            wind = weather['wind_speed']
            hum = weather['humidity']
        else:
            temp, wind, hum = "N/A", "N/A", "N/A"

        game_key_odds = f"{home}_{away}"
        if game_key_odds in odds_data:
            line = odds_data[game_key_odds].get('total', 'N/A')
            ml = odds_data[game_key_odds].get('ml', 'N/A')
            book = odds_data[game_key_odds].get('book', 'Unknown')
        else:
            line, ml, book = "N/A", "N/A", "N/A"
        
        alert = ""
        if temp != "N/A" and float(temp) > 85: alert = "🔥 OVER (Heat)"
        elif wind != "N/A" and float(wind) > 12: alert = "💨 OVER (Wind)"

        # Prepare the row data
        row_data = [today, home, away, hp, ap, book, ml, line, temp, wind, hum, alert, "", ""]
        
        # --- UPSERT EXECUTION ---
        game_key_sheet = f"{today}_{home}_{away}"
        
        if game_key_sheet in row_map:
            # Game exists! Update columns A through L (Leaving Actual/Result alone)
            row_num = row_map[game_key_sheet]
            # gspread format: sheet.update(range_name, [[values]])
            sheet.update(range_name=f"A{row_num}:L{row_num}", values=[row_data[:12]])
            print(f"🔄 Updated existing game: {away} @ {home}")
        else:
            # Game is new! Add to our append list
            games_to_append.append(row_data)
            print(f"➕ New game found: {away} @ {home}")

    if games_to_append:
        sheet.append_rows(games_to_append, value_input_option="USER_ENTERED")
        print(f"Appended {len(games_to_append)} new games to Master.")
    else:
        print("No new games to append. All existing games updated.")

if __name__ == "__main__":
    run_scraper()