import os, json, gspread, pytz, math
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import requests
import statcast_utils, db_manager
from odds_utils import get_mlb_odds
from weather_utils import get_stadium_weather
from stadiums import PARK_FACTORS, STADIUM_ORIENTATION 
from umpire_utils import get_umpire_multiplier
from pitcher_utils import get_pitcher_metrics
from bullpen_utils import get_bullpen_metrics, get_bullpen_fatigue
from hitter_utils import get_lineup_multiplier

load_dotenv(override=True)

def get_google_sheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_info = json.loads(os.getenv("GOOGLE_SHEETS_JSON"))
    return gspread.authorize(ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope))

def check_headers(sheet):
    headers = ["Date (CT)", "Home", "Away", "Home Pitcher", "Away Pitcher", "H ML", "A ML", "Spread", "O/U Total", "Exp Home Runs", "Exp Away Runs", "Proj Total", "Home SP Score", "Away SP Score", "Home BP Score", "Away BP Score", "Home Fatigue", "Away Fatigue", "Temp", "Wind", "Wind Dir", "Alerts", "Total Pick", "ML Pick", "Spread Pick", "Cumulative Stars", "Actual Score", "Result"]
    try: sheet.row_values(1)
    except: sheet.update(values=[headers], range_name='A1:AB1')

def calculate_wind_impact(home_team, wind_deg, wind_speed):
    if wind_deg == "N/A" or home_team not in STADIUM_ORIENTATION: return "Neutral"
    st_angle = STADIUM_ORIENTATION.get(home_team, 0)
    diff = abs(wind_deg - st_angle) % 360
    if diff > 180: diff = 360 - diff
    return "OUT" if (diff < 45 or diff > 315) and wind_speed > 10 else "Neutral"

def process_single_game(game, odds_data, today):
    home, away = game['teams']['home']['team']['name'], game['teams']['away']['team']['name']
    h_id, a_id = game['teams']['home']['team']['id'], game['teams']['away']['team']['id']
    
    hp_data = game['teams']['home'].get('probablePitcher', {})
    ap_data = game['teams']['away'].get('probablePitcher', {})
    
    hp_name, ap_name = hp_data.get('fullName', 'TBD'), ap_data.get('fullName', 'TBD')
    hp_id, ap_id = hp_data.get('id', None), ap_data.get('id', None)
    
    weather = get_stadium_weather(home, game.get('gameDate'), 'Open')
    temp = float(weather['temp']) if weather and weather['temp'] != "N/A" else 72.0
    w_sp = float(weather['wind_speed']) if weather and weather['wind_speed'] != "N/A" else 0
    w_deg = weather['wind_deg'] if weather and weather['wind_deg'] != "N/A" else 0
    
    wind_impact = calculate_wind_impact(home, w_deg, w_sp)
    hp_gb, ap_gb = statcast_utils.get_pitcher_gb_pct(hp_name), statcast_utils.get_pitcher_gb_pct(ap_name)
    hp_wind = 1.0 + ((w_sp - 5) * 0.006 * ((1.0 - hp_gb) / 0.57)) if wind_impact == "OUT" else 1.0
    ap_wind = 1.0 + ((w_sp - 5) * 0.006 * ((1.0 - ap_gb) / 0.57)) if wind_impact == "OUT" else 1.0
    
    hp_m = get_pitcher_metrics(hp_id) if hp_id else {'score': 0}
    ap_m = get_pitcher_metrics(ap_id) if ap_id else {'score': 0}
    h_bp, a_bp = get_bullpen_metrics(h_id), get_bullpen_metrics(a_id)
    h_f, a_f = get_bullpen_fatigue(h_id), get_bullpen_fatigue(a_id)
    h_mult, a_mult = get_lineup_multiplier(h_id, a_id), get_lineup_multiplier(a_id, h_id)
    
    park_f = PARK_FACTORS.get(home, 100)
    ump_m = get_umpire_multiplier(next((o['official']['fullName'] for o in game.get('officials', []) if o['officialType'] == 'Home Plate'), "Unknown"))
    
    env_m = (park_f / 100.0) * (1.0 + (temp - 72) * 0.0015) * ump_m
    exp_home = round((((ap_m['score'] * 0.66) + (a_bp['bp_score'] * 0.33) + h_f) * h_mult) * (env_m * ap_wind), 2)
    exp_away = round((((hp_m['score'] * 0.66) + (h_bp['bp_score'] * 0.33) + a_f) * a_mult) * (env_m * hp_wind), 2)
    
    odds = odds_data.get(f"{today}_{home}_{away}", {})
    
    total_pick, total_stars = "PASS", 0
    if odds.get('total') and odds.get('total') != "N/A":
        line = float(odds.get('total'))
        edge = abs((exp_home + exp_away) - line)
        if edge >= 0.75:
            stars = "★★★" if edge >= 2.0 else "★★" if edge >= 1.25 else "★"
            total_stars = len(stars)
            total_pick = f"{'OVER' if (exp_home+exp_away) > line else 'UNDER'} {line} | {stars}"
            
    db_data = {
        "game_id": f"{today}_{home}_{away}", "game_date": today, "home_team": home, "away_team": away,
        "home_pitcher": hp_name, "away_pitcher": ap_name,
        "home_sp_score": hp_m['score'], "away_sp_score": ap_m['score'],
        "home_bp_score": h_bp['bp_score'], "away_bp_score": a_bp['bp_score'],
        "home_fatigue": h_f, "away_fatigue": a_f,
        "home_lineup_mult": h_mult, "away_lineup_mult": a_mult,
        "park_factor": park_f, "umpire_multiplier": ump_m,
        "temp": temp, "wind_speed": w_sp, "wind_dir": weather.get('wind_dir'),
        "ml_home": odds.get('ml_home'), "ml_away": odds.get('ml_away'),
        "spread": odds.get('spread'), "ou_total": odds.get('total'),
        "projected_home_runs": exp_home, "projected_away_runs": exp_away
    }
    
    row = [today, home, away, hp_name, ap_name, odds.get('ml_home'), odds.get('ml_away'), odds.get('spread'), odds.get('total'), 
           exp_home, exp_away, round(exp_home + exp_away, 2), hp_m['score'], ap_m['score'], h_bp['bp_score'], a_bp['bp_score'], 
           h_f, a_f, temp, w_sp, weather.get('wind_dir'), "", total_pick, "PASS", "PASS", total_stars, "", ""]
    return row, db_data

def run_scraper():
    client = get_google_sheet_client()
    sheet = client.open("mlb-betting-app").worksheet("Master")
    check_headers(sheet)
    today = datetime.now(pytz.timezone('US/Central')).strftime('%Y-%m-%d')
    odds = get_mlb_odds()
    statcast_utils.load_statcast_data()
    
    games = requests.get(f"https://statsapi.mlb.com/api/v1/schedule/games/?sportId=1&date={today}&hydrate=probablePitcher,officials,weather").json().get('dates', [{}])[0].get('games', [])
    row_map = {f"{r[0]}_{r[1]}_{r[2]}": i + 1 for i, r in enumerate(sheet.get_all_values()) if len(r) >= 3}
    
    for game in games:
        row, db = process_single_game(game, odds, today)
        db_manager.upsert_game(db)
        key = f"{row[0]}_{row[1]}_{row[2]}"
        if key in row_map: sheet.update(values=[row[:26]], range_name=f"A{row_map[key]}:Z{row_map[key]}")
        else: sheet.append_row(row)

if __name__ == "__main__":
    run_scraper()