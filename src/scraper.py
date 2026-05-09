import os, requests, json, gspread, time, pytz
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

from odds_utils import get_mlb_odds
from weather_utils import get_stadium_weather
from stadiums import STADIUM_COORDS, PARK_FACTORS, STADIUM_ORIENTATION 
from umpire_utils import get_umpire_multiplier

load_dotenv(override=True)

def get_google_sheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    env_json = os.getenv("GOOGLE_SHEETS_JSON")
    creds_info = json.loads(env_json)
    return gspread.authorize(ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope))

def check_headers(sheet):
    headers = ["Date/Time (CT)", "Home", "Away", "Home Pitcher", "Away Pitcher", "Bookmaker", "ML Odds", "O/U Total", "Temp", "Wind", "Wind Dir", "Humidity", "Value Alert", "Actual Total", "Result"]
    first_row = sheet.row_values(1)
    if not first_row or first_row[0] == "":
        sheet.insert_row(headers, 1)
        sheet.format("A1:O1", {"textFormat": {"bold": True}})
        try: sheet.freeze(rows=1)
        except: pass

def calculate_wind_impact(home_team, wind_deg, wind_speed):
    if wind_deg == "N/A" or home_team not in STADIUM_ORIENTATION: return "Neutral"
    st_angle = STADIUM_ORIENTATION[home_team]
    diff = abs(wind_deg - st_angle) % 360
    if diff > 180: diff = 360 - diff
    if diff < 45 and wind_speed > 10: return "OUT"
    if diff > 135 and wind_speed > 10: return "IN"
    return "CROSS"

def run_scraper():
    print("--- Starting MLB Scraper (Full Version) ---")
    client = get_google_sheet_client()
    sheet = client.open("mlb-betting-app").worksheet("Master")
    check_headers(sheet)
    
    today = datetime.now(pytz.timezone('US/Central')).strftime('%Y-%m-%d')
    odds_data = get_mlb_odds()
    
    # HYDRATION: pitchers, officials (for umps), and weather (for roof status)
    url = f"https://statsapi.mlb.com/api/v1/schedule/games/?sportId=1&date={today}&hydrate=probablePitcher,officials,weather"
    response = requests.get(url).json()
    games = response.get('dates', [{}])[0].get('games', [])

    existing_rows = sheet.get_all_values()
    row_map = {f"{r[0]}_{r[1]}_{r[2]}": i + 1 for i, r in enumerate(existing_rows) if len(r) >= 3}
    games_to_append = []

    for game in games:
        home, away = game['teams']['home']['team']['name'], game['teams']['away']['team']['name']
        hp = game['teams']['home'].get('probablePitcher', {}).get('fullName', 'TBD')
        ap = game['teams']['away'].get('probablePitcher', {}).get('fullName', 'TBD')
        
        # 1. Official Umpire Check
        ump = next((o['official']['fullName'] for o in game.get('officials', []) if o['officialType'] == 'Home Plate'), "Unknown")
        
        # 2. Roof Status Check
        roof = game.get('weather', {}).get('condition', 'Open')
        weather = get_stadium_weather(home, game.get('gameDate'), roof)
        
        temp, w_sp, w_dir, hum, w_deg = (weather['temp'], weather['wind_speed'], weather['wind_dir'], weather['humidity'], weather['wind_deg']) if weather else ("N/A", "N/A", "N/A", "N/A", "N/A")

        # 3. Odds Matching
        matched_key = f"{today}_{home}_{away}"
        line = odds_data.get(matched_key, {}).get('total', 'N/A')
        ml = odds_data.get(matched_key, {}).get('ml', 'N/A')
        book = odds_data.get(matched_key, {}).get('book', 'DraftKings')

        # 4. Value Scoring
        park_f = PARK_FACTORS.get(home, 100)
        ump_m = get_umpire_multiplier(ump)
        wind_impact = calculate_wind_impact(home, w_deg, w_sp)
        
        alerts = []
        if temp != "N/A" and float(temp) > 85: alerts.append("🔥 HEAT")
        if park_f >= 108: alerts.append(f"🏟️ PARK ({park_f})")
        if ump_m > 1.05: alerts.append(f"⚖️ UMP ({ump})")
        if wind_impact == "OUT": alerts.append("💨 WIND OUT")
        elif wind_impact == "IN": alerts.append("🧤 WIND IN")

        if "WIND OUT" in str(alerts) and park_f > 105 and ump_m > 1.04:
            alerts.append("💣 NUCLEAR OVER")

        row_data = [today, home, away, hp, ap, book, ml, line, temp, w_sp, w_dir, hum, " | ".join(alerts), "", ""]
        
        if matched_key in row_map:
            sheet.update(range_name=f"A{row_map[matched_key]}:M{row_map[matched_key]}", values=[row_data[:13]])
        else:
            games_to_append.append(row_data)
        time.sleep(1)

    if games_to_append:
        sheet.append_rows(games_to_append, value_input_option="USER_ENTERED")
    print("✅ Success: All games synced.")

if __name__ == "__main__":
    run_scraper()