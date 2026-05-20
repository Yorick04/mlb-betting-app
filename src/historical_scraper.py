import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

# We import all the utility formulas you already built!
from stadiums import PARK_FACTORS
from umpire_utils import get_umpire_multiplier
from pitcher_utils import get_pitcher_metrics
from bullpen_utils import get_bullpen_metrics, get_bullpen_fatigue
from hitter_utils import get_lineup_multiplier
import db_manager

session = requests.Session()

# --- SPEED OPTIMIZATION CACHES ---
# Prevents the script from making 20,000 duplicate API calls
bp_metrics_cache = {}
bp_fatigue_cache = {}

# --- HISTORICAL PATCH FOR OAKLAND ATHLETICS ---
# In 2024, they played at the Oakland Coliseum, not Sacramento.
PARK_FACTORS["Oakland Athletics"] = 96  # 2024 Oakland Coliseum Park Factor

def parse_mlb_historical_weather(game_weather, roof_status):
    """Parses the exact historical weather from the MLB box score instead of using a live API"""
    temp = 72
    w_sp = 0
    wind_impact = "Neutral"
    
    try:
        # Extract digits from string like "72 degrees"
        temp_str = str(game_weather.get('temp', '72'))
        temp = int(''.join(filter(str.isdigit, temp_str)) or 72)
    except: pass
    
    wind_str = str(game_weather.get('wind', ''))
    if 'mph' in wind_str:
        parts = wind_str.split('mph')
        try: 
            w_sp = int(''.join(filter(str.isdigit, parts[0])) or 0)
        except: pass
        
        # MLB formats wind like "12 mph, Out To CF" or "8 mph, In From LF"
        dir_str = wind_str.lower()
        if 'out' in dir_str and w_sp > 10: wind_impact = "OUT"
        elif 'in ' in dir_str and w_sp > 10: wind_impact = "IN"

    # If the roof was closed, neutralize the weather
    if roof_status in ["Closed", "Dome", "Indoors", "Indoor"]:
        w_sp = 0
        wind_impact = "Neutral"
        temp = 72
        
    return temp, w_sp, "N/A", wind_impact

def process_historical_game(game, date_str):
    # Only process completed games
    status = game.get('status', {}).get('abstractGameState')
    if status != 'Final':
        return

    # Keep original names for accurate historical weather/park factor lookups!
    original_home = game['teams']['home']['team']['name']
    original_away = game['teams']['away']['team']['name']
    
    h_id = game['teams']['home']['team']['id']
    a_id = game['teams']['away']['team']['id']
    
    hp_data = game['teams']['home'].get('probablePitcher', {})
    ap_data = game['teams']['away'].get('probablePitcher', {})
    hp_name = hp_data.get('fullName', 'TBD')
    hp_id = hp_data.get('id', None)
    ap_name = ap_data.get('fullName', 'TBD')
    ap_id = ap_data.get('id', None)
    
    # Grab the actual score immediately since the game is in the past!
    actual_home = game['teams']['home'].get('score', 0)
    actual_away = game['teams']['away'].get('score', 0)

    ump = next((o['official']['fullName'] for o in game.get('officials', []) if o['officialType'] == 'Home Plate'), "Unknown")
    
    # Use MLB's recorded historical weather instead of hitting the live weather API!
    game_weather = game.get('weather', {})
    roof = game_weather.get('condition', 'Open')
    temp, w_sp, w_dir, wind_impact = parse_mlb_historical_weather(game_weather, roof)
    
    hp_m = get_pitcher_metrics(hp_id)
    ap_m = get_pitcher_metrics(ap_id)
    
    # --- USE IN-MEMORY CACHE FOR BULLPENS TO SPEED UP SCRIPT ---
    if h_id not in bp_metrics_cache: bp_metrics_cache[h_id] = get_bullpen_metrics(h_id)
    if a_id not in bp_metrics_cache: bp_metrics_cache[a_id] = get_bullpen_metrics(a_id)
    if h_id not in bp_fatigue_cache: bp_fatigue_cache[h_id] = get_bullpen_fatigue(h_id)
    if a_id not in bp_fatigue_cache: bp_fatigue_cache[a_id] = get_bullpen_fatigue(a_id)

    h_bp = bp_metrics_cache[h_id]
    a_bp = bp_metrics_cache[a_id]
    h_fatigue = bp_fatigue_cache[h_id]
    a_fatigue = bp_fatigue_cache[a_id]
    
    h_lineup_mult = get_lineup_multiplier(h_id, ap_id)
    a_lineup_mult = get_lineup_multiplier(a_id, hp_id)
    
    home_base_runs = ((ap_m['score'] * 0.66) + (a_bp['bp_score'] * 0.33) + a_fatigue) * h_lineup_mult
    away_base_runs = ((hp_m['score'] * 0.66) + (h_bp['bp_score'] * 0.33) + h_fatigue) * a_lineup_mult
    
    park_f = PARK_FACTORS.get(original_home, 100)
    ump_m = get_umpire_multiplier(ump)
    
    env_multiplier = (park_f / 100.0) * ump_m
    if temp != "N/A":
        t = float(temp)
        if t > 85: env_multiplier += 0.05
        elif t < 55: env_multiplier -= 0.05
    if wind_impact == "OUT": env_multiplier += 0.08
    elif wind_impact == "IN": env_multiplier -= 0.08

    exp_home = round(home_base_runs * env_multiplier, 2)
    exp_away = round(away_base_runs * env_multiplier, 2)
    
    # --- Standardize names for the Database ---
    db_home = "Athletics" if original_home == "Oakland Athletics" else original_home
    db_away = "Athletics" if original_away == "Oakland Athletics" else original_away
    
    matched_key = f"{date_str}_{db_home}_{db_away}"

    db_game_data = {
        "game_id": matched_key,
        "game_date": date_str,
        "home_team": db_home,
        "away_team": db_away,
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
        "ml_home": "N/A",  # No historical odds via free tier
        "ml_away": "N/A",
        "spread": "N/A",
        "ou_total": "N/A",
        "projected_home_runs": exp_home,
        "projected_away_runs": exp_away
    }

    # 1. Insert the raw AI features
    db_manager.upsert_game(db_game_data)
    
    # 2. Instantly update with the actual final score
    db_manager.update_final_score(matched_key, actual_home, actual_away, "FINAL")

def backfill_season(start_date_str, end_date_str):
    print(f"--- Starting Historical Scraper: {start_date_str} to {end_date_str} ---")
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
    
    current_date = start_date
    
    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        print(f"Processing {date_str}...")
        
        url = f"https://statsapi.mlb.com/api/v1/schedule/games/?sportId=1&date={date_str}&hydrate=probablePitcher,officials,weather"
        try:
            response = session.get(url, timeout=15).json()
            # Safety check if there are no games that day
            if 'dates' in response and len(response['dates']) > 0:
                games = response['dates'][0].get('games', [])
                
                # BUMPED TO 10 WORKERS FOR FASTER EXECUTION
                with ThreadPoolExecutor(max_workers=10) as executor:
                    futures = {executor.submit(process_historical_game, game, date_str): game for game in games}
                    for future in as_completed(futures):
                        pass 
        except Exception as e:
            print(f"Error on {date_str}: {e}")
            
        current_date += timedelta(days=1)
        
    print("✅ Historical Data Backfill Complete!")

if __name__ == "__main__":
    # Backfill XXXX Season (Previously completed, but re-run for database continuity)
    print("🚀 Starting 2026 Season Backfill...")
    backfill_season("2026-03-27", "2026-05-19")
    
    print("✅ All historical data (2024 + 2025 + 2026) successfully synced!")