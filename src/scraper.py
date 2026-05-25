import os, json, gspread, time, pytz, math
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import statcast_utils

from odds_utils import get_mlb_odds
from weather_utils import get_stadium_weather
from stadiums import STADIUM_COORDS, PARK_FACTORS, STADIUM_ORIENTATION 
from umpire_utils import get_umpire_multiplier
from pitcher_utils import get_pitcher_metrics
from bullpen_utils import get_bullpen_metrics, get_bullpen_fatigue
from hitter_utils import get_lineup_multiplier
import db_manager

load_dotenv(override=True)
session = requests.Session()

def get_google_sheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_info = json.loads(os.getenv("GOOGLE_SHEETS_JSON"))
    return gspread.authorize(ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope))

def check_headers(sheet):
    headers = [
        "Date (CT)", "Home", "Away", "Home Pitcher", "Away Pitcher", 
        "H ML", "A ML", "Spread", "O/U Total", 
        "Exp Home Runs", "Exp Away Runs", "Proj Total",
        "Home SP Score", "Away SP Score", "Home BP Score", "Away BP Score", 
        "Home Fatigue", "Away Fatigue", "Temp", "Wind", "Wind Dir", "Alerts",
        "Total Pick", "ML Pick", "Spread Pick", "Cumulative Stars", "Actual Score", "Result"
    ]
    try: first_row = sheet.row_values(1)
    except: first_row = []

    if not first_row or len(first_row) != len(headers):
        sheet.update(values=[["" for _ in range(30)]], range_name='A1:AD1') 
        sheet.update(values=[headers], range_name='A1:AB1')
        sheet.format("A1:AB1", {"textFormat": {"bold": True}})

def implied_probability(american_odds):
    if american_odds == "N/A": return 0
    odds = float(american_odds)
    return abs(odds) / (abs(odds) + 100) if odds < 0 else 100 / (odds + 100)

def calculate_wind_impact(home_team, wind_deg, wind_speed):
    if wind_deg == "N/A" or home_team not in STADIUM_ORIENTATION: return "Neutral"
    st_angle = STADIUM_ORIENTATION[home_team]
    diff = abs(wind_deg - st_angle) % 360
    if diff > 180: diff = 360 - diff
    if diff < 45 and wind_speed > 10: return "OUT"
    if diff > 135 and wind_speed > 10: return "IN"
    return "CROSS"

def process_single_game(game, odds_data, today):
    home, away = game['teams']['home']['team']['name'], game['teams']['away']['team']['name']
    h_id, a_id = game['teams']['home']['team']['id'], game['teams']['away']['team']['id']
    
    hp_data = game['teams']['home'].get('probablePitcher', {})
    ap_data = game['teams']['away'].get('probablePitcher', {})
    hp_name, hp_id = hp_data.get('fullName', 'TBD'), hp_data.get('id', None)
    ap_name, ap_id = ap_data.get('fullName', 'TBD'), ap_data.get('id', None)
    
    # --- STATCAST XSTATS DATA PULL ---
    h_sp_xera = statcast_utils.get_pitcher_xera(hp_name) if hp_name != 'TBD' else None
    a_sp_xera = statcast_utils.get_pitcher_xera(ap_name) if ap_name != 'TBD' else None
    
    h_lineup_xba = statcast_utils.get_lineup_xba(home)
    a_lineup_xba = statcast_utils.get_lineup_xba(away)
    h_lineup_xslg = statcast_utils.get_lineup_xslg(home)
    a_lineup_xslg = statcast_utils.get_lineup_xslg(away)
    
    ump = next((o['official']['fullName'] for o in game.get('officials', []) if o['officialType'] == 'Home Plate'), "Unknown")
    roof = game.get('weather', {}).get('condition', 'Open')
    weather = get_stadium_weather(home, game.get('gameDate'), roof)
    temp, w_sp, w_dir, hum, w_deg = (weather['temp'], weather['wind_speed'], weather['wind_dir'], weather['humidity'], weather['wind_deg']) if weather else ("N/A", "N/A", "N/A", "N/A", "N/A")

    matched_key = f"{today}_{home}_{away}"
    odds = odds_data.get(matched_key, {})
    book_name = "DraftKings"
    
    line = odds.get('total', 'N/A')
    ml_h = odds.get('ml_home', 'N/A')
    ml_a = odds.get('ml_away', 'N/A')
    rl_hp = odds.get('rl_home_point', 'N/A')
    rl_hc = odds.get('rl_home_price', 'N/A')
    
    hp_m = get_pitcher_metrics(hp_id)
    ap_m = get_pitcher_metrics(ap_id)
    h_bp = get_bullpen_metrics(h_id)
    a_bp = get_bullpen_metrics(a_id)
    h_fatigue = get_bullpen_fatigue(h_id)
    a_fatigue = get_bullpen_fatigue(a_id)
    
    h_lineup_mult = get_lineup_multiplier(h_id, ap_id)
    a_lineup_mult = get_lineup_multiplier(a_id, hp_id)
    
    home_base_runs = ((ap_m['score'] * 0.66) + (a_bp['bp_score'] * 0.33) + h_fatigue) * h_lineup_mult
    away_base_runs = ((hp_m['score'] * 0.66) + (h_bp['bp_score'] * 0.33) + a_fatigue) * a_lineup_mult
    
    park_f = PARK_FACTORS.get(home, 100)
    ump_m = get_umpire_multiplier(ump)
    wind_impact = calculate_wind_impact(home, w_deg, w_sp)
    
    env_multiplier = (park_f / 100.0) * ump_m
    if temp != "N/A":
        t = float(temp)
        if t > 85: env_multiplier += 0.05
        elif t < 55: env_multiplier -= 0.05
    if wind_impact == "OUT": env_multiplier += 0.08
    elif wind_impact == "IN": env_multiplier -= 0.08

    exp_home = round(home_base_runs * env_multiplier, 2)
    exp_away = round(away_base_runs * env_multiplier, 2)
    expected_total = round(exp_home + exp_away, 2)
    
    total_pick, ml_pick, spread_pick = "PASS", "PASS", "PASS"
    total_stars = 0
    
    if line != "N/A":
        edge = abs(expected_total - float(line))
        if edge >= 0.75:
            stars = "★★★" if edge >= 2.0 else "★★" if edge >= 1.25 else "★"
            total_stars += len(stars)
            direction = "OVER" if expected_total > float(line) else "UNDER"
            total_pick = f"{direction} {line} [{book_name}] | {stars}"

    if exp_home > 0 and exp_away > 0 and ml_h != "N/A" and ml_a != "N/A":
        model_h_prob = (exp_home**1.83) / (exp_home**1.83 + exp_away**1.83)
        book_h_prob, book_a_prob = implied_probability(ml_h), implied_probability(ml_a)
        h_edge, a_edge = (model_h_prob - book_h_prob), ((1.0 - model_h_prob) - book_a_prob)
        if book_h_prob > 0 and h_edge > 0.05:
            stars = "★★★" if h_edge > 0.12 else "★★" if h_edge > 0.08 else "★"
            total_stars += len(stars)
            ml_pick = f"HOME {ml_h} [{book_name}] | {stars}"
        elif book_a_prob > 0 and a_edge > 0.05:
            stars = "★★★" if a_edge > 0.12 else "★★" if a_edge > 0.08 else "★"
            total_stars += len(stars)
            ml_pick = f"AWAY {ml_a} [{book_name}] | {stars}"

    if rl_hp != "N/A" and odds.get('rl_away_point') != "N/A":
        h_point, a_point = float(rl_hp), float(odds.get('rl_away_point'))
        mean_run_diff = exp_home - exp_away 
        var_run_diff = exp_home + exp_away
        if var_run_diff > 0:
            z_score_h = (mean_run_diff - (-h_point)) / math.sqrt(var_run_diff)
            prob_h_cover = 0.5 * (1 + math.erf(z_score_h / math.sqrt(2)))
            z_score_a = (-mean_run_diff - (-a_point)) / math.sqrt(var_run_diff)
            prob_a_cover = 0.5 * (1 + math.erf(z_score_a / math.sqrt(2)))
        else:
            prob_h_cover, prob_a_cover = 0, 0
            
        book_h_rl_prob = implied_probability(rl_hc)
        book_a_rl_prob = implied_probability(odds.get('rl_away_price'))
        h_edge = prob_h_cover - book_h_rl_prob
        a_edge = prob_a_cover - book_a_rl_prob
        
        if book_h_rl_prob > 0 and h_edge > 0.05:
            stars = "★★★" if h_edge >= 0.12 else "★★" if h_edge >= 0.08 else "★"
            total_stars += len(stars)
            sign = "+" if h_point > 0 else ""
            spread_pick = f"HOME {sign}{h_point} ({rl_hc}) [{book_name}] | {stars}"
        elif book_a_rl_prob > 0 and a_edge > 0.05:
            stars = "★★★" if a_edge >= 0.12 else "★★" if a_edge >= 0.08 else "★"
            total_stars += len(stars)
            sign = "+" if a_point > 0 else ""
            spread_pick = f"AWAY {sign}{a_point} ({odds.get('rl_away_price')}) [{book_name}] | {stars}"

    alerts = [a for a in [
        "🔥 HEAT" if temp != "N/A" and float(temp) > 85 else None,
        f"🏟️ PARK ({park_f})" if park_f >= 108 else None,
        f"⚖️ UMP ({ump})" if ump_m > 1.05 else None,
        "💨 WIND OUT" if wind_impact == "OUT" else None,
        "🧤 WIND IN" if wind_impact == "IN" else None,
        "🔋 GASSED BP" if h_fatigue > 0.2 or a_fatigue > 0.2 else None
    ] if a]

    spread_fmt = f"{rl_hp} ({rl_hc})" if rl_hp != "N/A" else "N/A"
    
    # --- SQLITE DATABASE DICTIONARY ---
    db_game_data = {
        "game_id": matched_key,
        "game_date": today,
        "home_team": home,
        "away_team": away,
        "home_pitcher": hp_name,
        "away_pitcher": ap_name,
        "home_sp_score": hp_m['score'],
        "away_sp_score": ap_m['score'],
        "home_bp_score": h_bp['bp_score'],
        "away_bp_score": a_bp['bp_score'],
        "home_fatigue": h_fatigue,
        "away_fatigue": a_fatigue,
        "home_lineup_mult": h_lineup_mult, 
        "away_lineup_mult": a_lineup_mult, 
        "temp": temp,
        "wind_speed": w_sp,
        "wind_dir": w_dir,
        "park_factor": park_f,
        "umpire_multiplier": ump_m,
        "ml_home": ml_h,
        "ml_away": ml_a,
        "spread": spread_fmt,
        "ou_total": line,
        "projected_home_runs": exp_home,
        "projected_away_runs": exp_away,
        "home_sp_xERA": h_sp_xera,
        "away_sp_xERA": a_sp_xera,
        "home_lineup_xBA": h_lineup_xba,
        "away_lineup_xBA": a_lineup_xba,
        "home_lineup_xSLG": h_lineup_xslg,
        "away_lineup_xSLG": a_lineup_xslg
    }

    sheet_row = [
        today, home, away, hp_name, ap_name, 
        ml_h, ml_a, spread_fmt, line,
        exp_home, exp_away, expected_total,
        hp_m['score'], ap_m['score'], h_bp['bp_score'], a_bp['bp_score'], 
        h_fatigue, a_fatigue, temp, w_sp, w_dir, " | ".join(alerts), 
        total_pick, ml_pick, spread_pick, total_stars, 
        "", "" 
    ]
    
    return sheet_row, db_game_data

def run_scraper():
    print("--- Starting MLB Scraper (Database & Sheets Sync) ---")
    client = get_google_sheet_client()
    sheet = client.open("mlb-betting-app").worksheet("Master")
    check_headers(sheet)
    
    today = datetime.now(pytz.timezone('US/Central')).strftime('%Y-%m-%d')
    odds_data = get_mlb_odds()
    
    # Pre-load the cache outside of the thread pool so we only ping the API once
    statcast_utils.load_statcast_data()
    
    url = f"https://statsapi.mlb.com/api/v1/schedule/games/?sportId=1&date={today}&hydrate=probablePitcher,officials,weather"
    response = session.get(url).json()
    games = response.get('dates', [{}])[0].get('games', [])

    existing_rows = sheet.get_all_values()
    row_map = {f"{r[0]}_{r[1]}_{r[2]}": i + 1 for i, r in enumerate(existing_rows) if len(r) >= 3}
    games_to_append = []

    # Reduced workers to 3 to prevent Weather API rate limits (429 errors)
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(process_single_game, game, odds_data, today): game for game in games}
        
        for future in as_completed(futures):
            sheet_row_data, db_game_data = future.result()
            
            db_manager.upsert_game(db_game_data)
            
            matched_key = f"{sheet_row_data[0]}_{sheet_row_data[1]}_{sheet_row_data[2]}"
            if matched_key in row_map:
                sheet.update(values=[sheet_row_data[:26]], range_name=f"A{row_map[matched_key]}:Z{row_map[matched_key]}")
            else:
                games_to_append.append(sheet_row_data)

    if games_to_append:
        sheet.append_rows(games_to_append, value_input_option="USER_ENTERED")
    print("✅ Success: SQLite DB and Google Sheets sync complete.")

if __name__ == "__main__":
    run_scraper()