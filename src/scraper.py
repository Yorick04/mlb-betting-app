import os, json, gspread, pytz, math
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import requests

# Custom Modules
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

def run_scraper():
    print("--- ⚾ Starting Daily MLB Scraper ---")
    
    # 1. Initialize Database
    db_conn = db_manager.get_connection()
    db_cursor = db_conn.cursor()
    
    # 2. Fetch Third-Party Data
    print("Fetching live DraftKings odds...")
    odds = get_mlb_odds()
    
    statcast_utils.load_statcast_data()
    
    # 3. Get Today's Schedule
    today = datetime.now(pytz.timezone('US/Central')).strftime('%Y-%m-%d')
    url = f"https://statsapi.mlb.com/api/v1/schedule/games/?sportId=1&date={today}&hydrate=probablePitcher,officials,weather"
    
    print(f"Fetching MLB Schedule for {today}...")
    try:
        resp = requests.get(url, timeout=15).json()
        games = resp.get('dates', [{}])[0].get('games', [])
    except Exception as e:
        print(f"❌ Failed to fetch MLB schedule: {e}")
        return
        
    if not games:
        print("⚾ No games found for today.")
        return

    # 4. Connect to Google Sheets
    try:
        client = get_google_sheet_client()
        sheet = client.open("mlb-betting-app").worksheet("Master")
        existing_rows = sheet.get_all_records()
    except Exception as e:
        print(f"⚠️ Google Sheets connection failed (Data will still save to DB): {e}")
        existing_rows = []
        sheet = None
        
    rows_to_insert = []
    cells_to_update = [] # Holds updates for games that already exist on the sheet
    
    # 5. Process Each Game
    for g in games:
        status = g['status']['abstractGameState']
        if status == 'Final':
            continue  
            
        home_team = g['teams']['home']['team']['name']
        away_team = g['teams']['away']['team']['name']
        home_id = g['teams']['home']['team']['id']
        away_id = g['teams']['away']['team']['id']
        
        print(f"\nProcessing: {away_team} @ {home_team}")
        
        db_game_id = f"{today}_{home_team}_{away_team}"
        
        # --- Pitcher Logic ---
        hp_id = g['teams']['home'].get('probablePitcher', {}).get('id', "TBD")
        ap_id = g['teams']['away'].get('probablePitcher', {}).get('id', "TBD")
        hp_name = g['teams']['home'].get('probablePitcher', {}).get('fullName', "TBD")
        ap_name = g['teams']['away'].get('probablePitcher', {}).get('fullName', "TBD")
        
        hp_metrics = get_pitcher_metrics(hp_id)
        ap_metrics = get_pitcher_metrics(ap_id)
        
        hp_xera = statcast_utils.get_pitcher_xera(hp_name)
        ap_xera = statcast_utils.get_pitcher_xera(ap_name)
        hp_score = hp_xera if hp_xera else hp_metrics.get('score', 4.50)
        ap_score = ap_xera if ap_xera else ap_metrics.get('score', 4.50)
        # Cap extreme small-sample outliers so they don't break the StandardScaler
        hp_score = min(hp_score, 8.50)
        ap_score = min(ap_score, 8.50)
        
        # --- Bullpen & Lineup Logic ---
        h_bp = get_bullpen_metrics(home_id)
        a_bp = get_bullpen_metrics(away_id)
        
        h_f = get_bullpen_fatigue(home_id)
        a_f = get_bullpen_fatigue(away_id)
        
        h_lineup = get_lineup_multiplier(home_id, ap_id)
        a_lineup = get_lineup_multiplier(away_id, hp_id)
        
        # --- Weather & Environment ---
        roof = g.get('weather', {}).get('condition', "Open")
        weather = get_stadium_weather(home_team, roof_status=roof)
        temp = weather.get('temp', 72)
        wind_sp = weather.get('wind_speed', 0)
        wind_dir = weather.get('wind_dir', "N/A")
        
        park_factor = PARK_FACTORS.get(home_team, 100)
        
        # --- Umpire Logic ---
        umpire_name = "TBD"
        for off in g.get('officials', []):
            if off.get('officialType') == 'Home Plate':
                umpire_name = off.get('official', {}).get('fullName')
                break
        ump_mult = get_umpire_multiplier(umpire_name)
        
        # ---------------------------------------------------------
        # 🛡️ THE ODDS MEMORY PATCH 🛡️
        # ---------------------------------------------------------
        game_odds = odds.get(f"{home_team}_{away_team}", {})
        ml_home = game_odds.get('ml_home')
        ml_away = game_odds.get('ml_away')
        spread = game_odds.get('spread')
        ou_total = game_odds.get('ou_total')

        # If The Odds API dropped the game (because it started or wasn't posted), rescue our morning odds from SQLite
        if ml_home is None or ml_home == "N/A" or ou_total is None or ou_total == "N/A":
            db_cursor.execute("SELECT ml_home, ml_away, spread, ou_total FROM game_logs WHERE game_id = ?", (db_game_id,))
            saved = db_cursor.fetchone()
            
            if saved and saved[0] is not None and str(saved[0]) != "N/A":
                ml_home, ml_away, spread, ou_total = saved
                print(f"   🔄 Rescued morning odds for {home_team} from database.")
                
        ml_home = ml_home if ml_home is not None else "N/A"
        ml_away = ml_away if ml_away is not None else "N/A"
        spread = spread if spread is not None else "N/A"
        ou_total = ou_total if ou_total is not None else "N/A"
        # ---------------------------------------------------------

        # --- 6. Save to SQLite Database ---
        clean_data = {
            "game_id": db_game_id, "game_date": today, "home_team": home_team, "away_team": away_team,
            "home_pitcher": hp_name, "away_pitcher": ap_name, "home_sp_score": hp_score, "away_sp_score": ap_score,
            "home_bp_score": h_bp.get('bp_score', 4.50), "away_bp_score": a_bp.get('bp_score', 4.50),
            "home_fatigue": h_f, "away_fatigue": a_f, "home_lineup_mult": h_lineup, "away_lineup_mult": a_lineup,
            "temp": temp, "wind_speed": wind_sp, "wind_dir": wind_dir, "park_factor": park_factor, "umpire_multiplier": ump_mult,
            "ml_home": None if ml_home == "N/A" else ml_home, 
            "ml_away": None if ml_away == "N/A" else ml_away, 
            "spread": None if spread == "N/A" else spread, 
            "ou_total": None if ou_total == "N/A" else ou_total,
            "projected_home_runs": 0.0, "projected_away_runs": 0.0
        }

        # Use COALESCE to ensure we never overwrite good odds with N/A on a second run
        sql = '''
        INSERT INTO game_logs (
            game_id, game_date, home_team, away_team, home_pitcher, away_pitcher,
            home_sp_score, away_sp_score, home_bp_score, away_bp_score, home_fatigue, away_fatigue,
            home_lineup_mult, away_lineup_mult, temp, wind_speed, wind_dir, park_factor, umpire_multiplier,
            ml_home, ml_away, spread, ou_total, projected_home_runs, projected_away_runs, status
        ) VALUES (
            :game_id, :game_date, :home_team, :away_team, :home_pitcher, :away_pitcher,
            :home_sp_score, :away_sp_score, :home_bp_score, :away_bp_score, :home_fatigue, :away_fatigue,
            :home_lineup_mult, :away_lineup_mult, :temp, :wind_speed, :wind_dir, :park_factor, :umpire_multiplier,
            :ml_home, :ml_away, :spread, :ou_total, :projected_home_runs, :projected_away_runs, 'PENDING'
        )
        ON CONFLICT(game_id) DO UPDATE SET
            home_pitcher=excluded.home_pitcher, away_pitcher=excluded.away_pitcher,
            home_sp_score=excluded.home_sp_score, away_sp_score=excluded.away_sp_score,
            home_bp_score=excluded.home_bp_score, away_bp_score=excluded.away_bp_score,
            home_lineup_mult=excluded.home_lineup_mult, away_lineup_mult=excluded.away_lineup_mult,
            ml_home=COALESCE(excluded.ml_home, game_logs.ml_home), ml_away=COALESCE(excluded.ml_away, game_logs.ml_away),
            spread=COALESCE(excluded.spread, game_logs.spread), ou_total=COALESCE(excluded.ou_total, game_logs.ou_total),
            temp=excluded.temp, wind_speed=excluded.wind_speed, wind_dir=excluded.wind_dir,
            home_fatigue=excluded.home_fatigue, away_fatigue=excluded.away_fatigue, umpire_multiplier=excluded.umpire_multiplier;
        '''
        try:
            db_cursor.execute(sql, clean_data)
            db_conn.commit()
        except Exception as e:
            print(f"❌ Error saving to database: {e}")

        # --- 7. Append OR Update Google Sheet ---
        if sheet:
            is_new = True
            row_idx = None
            for i, r in enumerate(existing_rows, start=2): # start=2 offsets header row
                if r.get('Date (CT)') == today and r.get('Home') == home_team and r.get('Away') == away_team:
                    is_new = False
                    row_idx = i
                    break
                    
            if is_new:
                # Add entirely new row. Leave AI prediction columns as "N/A" and "PASS"
                row = [
                    today, home_team, away_team, hp_name, ap_name, ml_home, ml_away, spread, ou_total, 
                    "N/A", "N/A", "N/A", round(hp_score, 2), round(ap_score, 2), 
                    round(h_bp.get('bp_score', 4.5), 2), round(a_bp.get('bp_score', 4.5), 2), 
                    round(h_f, 2), round(a_f, 2), temp, wind_sp, wind_dir, "", 
                    "PASS", "PASS", "PASS", "", "", ""
                ]
                rows_to_insert.append(row)
            else:
                # UPDATE existing row with fresh odds, live weather, and pitcher names
                if hp_name and hp_name != "TBD": cells_to_update.append(gspread.Cell(row=row_idx, col=4, value=hp_name))
                if ap_name and ap_name != "TBD": cells_to_update.append(gspread.Cell(row=row_idx, col=5, value=ap_name))
                
                # Only update odds cells if we actually pulled valid numbers
                if ml_home not in ["N/A", None]: cells_to_update.append(gspread.Cell(row=row_idx, col=6, value=ml_home))
                if ml_away not in ["N/A", None]: cells_to_update.append(gspread.Cell(row=row_idx, col=7, value=ml_away))
                if spread not in ["N/A", None]: cells_to_update.append(gspread.Cell(row=row_idx, col=8, value=spread))
                if ou_total not in ["N/A", None]: cells_to_update.append(gspread.Cell(row=row_idx, col=9, value=ou_total))
                
                # Update live weather (Cols S=19, T=20, U=21)
                cells_to_update.append(gspread.Cell(row=row_idx, col=19, value=temp))
                cells_to_update.append(gspread.Cell(row=row_idx, col=20, value=wind_sp))
                cells_to_update.append(gspread.Cell(row=row_idx, col=21, value=wind_dir))
            
    # Execute batch writes to Google Sheets
    if sheet and rows_to_insert:
        sheet.append_rows(rows_to_insert)
        print(f"\n✅ Appended {len(rows_to_insert)} new games to Google Sheet.")
        
    if sheet and cells_to_update:
        sheet.update_cells(cells_to_update)
        print(f"\n✅ Updated Odds, Weather, and Pitchers for {len(cells_to_update)//9} existing games in the Google Sheet.")
        
    db_conn.close()
    print("--- ⚾ Scraper Complete ---")

if __name__ == "__main__":
    run_scraper()