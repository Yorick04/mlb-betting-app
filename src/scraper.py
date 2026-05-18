import os, requests, json, gspread, time, pytz
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# Your utility imports
from odds_utils import get_mlb_odds
from weather_utils import get_stadium_weather
from stadiums import STADIUM_COORDS, PARK_FACTORS, STADIUM_ORIENTATION 
from umpire_utils import get_umpire_multiplier
from pitcher_utils import get_pitcher_metrics
from bullpen_utils import get_bullpen_metrics, get_bullpen_fatigue

load_dotenv(override=True)

def get_google_sheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    env_json = os.getenv("GOOGLE_SHEETS_JSON")
    creds_info = json.loads(env_json)
    return gspread.authorize(ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope))

def check_headers(sheet):
    # The Definitive 24-Column Layout
    headers = [
        "Date/Time (CT)", "Home", "Away", "Home Pitcher", "Away Pitcher", 
        "Bookmaker", "ML Odds", "O/U Total", "Projected Total", 
        "Home SP Score", "Away SP Score", "Home BP Score", "Away BP Score", 
        "Home BP Fatigue", "Away BP Fatigue", "Temp", "Wind", "Wind Dir", 
        "Humidity", "Value Alert", "Model Pick", "Confidence Score", 
        "Actual Total", "Result"
    ]
    try:
        first_row = sheet.row_values(1)
    except:
        first_row = []

    if not first_row or len(first_row) != len(headers):
        print("--- Rebuilding Sheet Headers to 24 Columns ---")
        # Safety wipe out to column AD to clear out old orphan data
        sheet.update(values=[["" for _ in range(30)]], range_name='A1:AD1') 
        
        # Write clean headers
        sheet.update(values=[headers], range_name='A1:X1')
        sheet.format("A1:X1", {"textFormat": {"bold": True}})
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
    print("--- Starting MLB Scraper (Bridge Model Integrated) ---")
    client = get_google_sheet_client()
    sheet = client.open("mlb-betting-app").worksheet("Master")
    check_headers(sheet)
    
    today = datetime.now(pytz.timezone('US/Central')).strftime('%Y-%m-%d')
    odds_data = get_mlb_odds()
    
    url = f"https://statsapi.mlb.com/api/v1/schedule/games/?sportId=1&date={today}&hydrate=probablePitcher,officials,weather"
    response = requests.get(url).json()
    games = response.get('dates', [{}])[0].get('games', [])

    existing_rows = sheet.get_all_values()
    row_map = {f"{r[0]}_{r[1]}_{r[2]}": i + 1 for i, r in enumerate(existing_rows) if len(r) >= 3}
    games_to_append = []

    for game in games:
        home, away = game['teams']['home']['team']['name'], game['teams']['away']['team']['name']
        h_id, a_id = game['teams']['home']['team']['id'], game['teams']['away']['team']['id']
        
        # Pitcher Info
        hp_data = game['teams']['home'].get('probablePitcher', {})
        ap_data = game['teams']['away'].get('probablePitcher', {})
        hp_name, hp_id = hp_data.get('fullName', 'TBD'), hp_data.get('id', None)
        ap_name, ap_id = ap_data.get('fullName', 'TBD'), ap_data.get('id', None)
        
        ump = next((o['official']['fullName'] for o in game.get('officials', []) if o['officialType'] == 'Home Plate'), "Unknown")
        roof = game.get('weather', {}).get('condition', 'Open')
        weather = get_stadium_weather(home, game.get('gameDate'), roof)
        
        temp, w_sp, w_dir, hum, w_deg = (weather['temp'], weather['wind_speed'], weather['wind_dir'], weather['humidity'], weather['wind_deg']) if weather else ("N/A", "N/A", "N/A", "N/A", "N/A")

        matched_key = f"{today}_{home}_{away}"
        line = odds_data.get(matched_key, {}).get('total', 'N/A')
        ml = odds_data.get(matched_key, {}).get('ml', 'N/A')
        book = odds_data.get(matched_key, {}).get('book', 'DraftKings')

        # 1. Fetch Metrics
        hp_m = get_pitcher_metrics(hp_id)
        ap_m = get_pitcher_metrics(ap_id)
        h_bp = get_bullpen_metrics(h_id)
        a_bp = get_bullpen_metrics(a_id)
        h_fatigue = get_bullpen_fatigue(h_id)
        a_fatigue = get_bullpen_fatigue(a_id)
        
        # 2. Bridge Math: Starter (66%) + Bullpen (33%) + Fatigue
        h_score = (hp_m['score'] * 0.66) + (h_bp['bp_score'] * 0.33) + h_fatigue
        a_score = (ap_m['score'] * 0.66) + (a_bp['bp_score'] * 0.33) + a_fatigue
        
        park_f = PARK_FACTORS.get(home, 100)
        ump_m = get_umpire_multiplier(ump)
        wind_impact = calculate_wind_impact(home, w_deg, w_sp)
        
        expected_total = (h_score + a_score) * (park_f / 100.0) * ump_m
        
        if temp != "N/A":
            t = float(temp)
            if t > 85: expected_total += 0.3
            elif t < 55: expected_total -= 0.3
        if wind_impact == "OUT": expected_total += 0.6
        elif wind_impact == "IN": expected_total -= 0.6
        
        expected_total = round(expected_total, 2)
        
        # 3. Decision Logic
        model_pick = "PASS"
        confidence_score = 0
        if line != "N/A":
            book_line = float(line)
            edge = abs(expected_total - book_line)
            if edge >= 0.75:
                model_pick = "OVER" if expected_total > book_line else "UNDER"
                model_pick = f"{model_pick} {book_line}"
                if edge >= 1.75: confidence_score = 3
                elif edge >= 1.25: confidence_score = 2
                else: confidence_score = 1

        alerts = []
        if temp != "N/A" and float(temp) > 85: alerts.append("🔥 HEAT")
        if park_f >= 108: alerts.append(f"🏟️ PARK ({park_f})")
        if ump_m > 1.05: alerts.append(f"⚖️ UMP ({ump})")
        if wind_impact == "OUT": alerts.append("💨 WIND OUT")
        elif wind_impact == "IN": alerts.append("🧤 WIND IN")
        if h_fatigue > 0.2 or a_fatigue > 0.2: alerts.append("🔋 GASSED BP")

        # 24-Column row data setup
        row_data = [
            today, home, away, hp_name, ap_name, book, ml, line, 
            expected_total, hp_m['score'], ap_m['score'], 
            h_bp['bp_score'], a_bp['bp_score'], h_fatigue, a_fatigue, 
            temp, w_sp, w_dir, hum, " | ".join(alerts), 
            model_pick, confidence_score, 
            "", "" # Cols 23 & 24: Actual and Result
        ]
        
        if matched_key in row_map:
            # Update A through V (1 to 22) to keep columns 23 and 24 safe from overrides
            sheet.update(values=[row_data[:22]], range_name=f"A{row_map[matched_key]}:V{row_map[matched_key]}")
        else:
            games_to_append.append(row_data)
        time.sleep(1)

    if games_to_append:
        sheet.append_rows(games_to_append, value_input_option="USER_ENTERED")
    print("✅ Success: Bridge Model sync complete.")

if __name__ == "__main__":
    run_scraper()