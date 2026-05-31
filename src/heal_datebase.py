import sqlite3
import requests
import time
from datetime import datetime, timedelta
import pytz

# Persistent session to keep the connection open
session = requests.Session()

# 🧠 THE MEMORY CACHE
# These dictionaries store API responses so we never download the same game twice
SCHEDULE_CACHE = {}
BOXSCORE_CACHE = {}

def get_team_ids():
    """Fetches all MLB team IDs to map database names to API IDs."""
    teams = requests.get("https://statsapi.mlb.com/api/v1/teams?sportId=1").json()['teams']
    return {t['name']: t['id'] for t in teams}

def get_fatigue_cached(team_id, game_date_str):
    """A hyper-fast, cached version of the bullpen fatigue calculator."""
    tz = pytz.timezone('US/Central')
    game_date = datetime.strptime(game_date_str, '%Y-%m-%d').replace(tzinfo=tz)
        
    start_date = (game_date - timedelta(days=3)).strftime('%Y-%m-%d')
    end_date = (game_date - timedelta(days=1)).strftime('%Y-%m-%d')
    
    fatigue_penalty = 0.0
    
    # 1. Check Schedule Cache
    sched_key = f"{team_id}_{start_date}_{end_date}"
    if sched_key in SCHEDULE_CACHE:
        resp = SCHEDULE_CACHE[sched_key]
    else:
        schedule_url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&teamId={team_id}&startDate={start_date}&endDate={end_date}"
        try:
            resp = session.get(schedule_url, timeout=10).json()
            SCHEDULE_CACHE[sched_key] = resp
            time.sleep(0.05) # Polite delay ONLY when we actually hit the network
        except Exception:
            return 0.0

    for date_obj in resp.get('dates', []):
        for game in date_obj.get('games', []):
            game_pk = game.get('gamePk')
            if not game_pk:
                continue
                
            is_home = (game['teams']['home']['team']['id'] == team_id)
            team_side = 'home' if is_home else 'away'
            
            # 2. Check Boxscore Cache
            if game_pk in BOXSCORE_CACHE:
                box_resp = BOXSCORE_CACHE[game_pk]
            else:
                box_url = f"https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore"
                try:
                    box_resp = session.get(box_url, timeout=10).json()
                    BOXSCORE_CACHE[game_pk] = box_resp
                    time.sleep(0.05) # Polite delay ONLY when we actually hit the network
                except Exception:
                    continue
            
            # 3. Calculate Pitchers Used
            try:
                pitchers = box_resp['teams'][team_side].get('pitchers', [])
                if len(pitchers) > 5:
                    fatigue_penalty += 0.15
            except Exception:
                pass
                
    return round(fatigue_penalty, 2)

def heal_database():
    print("🏥 Starting High-Speed Database Healing Process...")
    team_map = get_team_ids()
    
    conn = sqlite3.connect("mlb_historical_data.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT game_id, game_date, home_team, away_team FROM game_logs WHERE home_fatigue = 0.0 OR home_fatigue IS NULL")
    games = cursor.fetchall()
    
    total_games = len(games)
    if total_games == 0:
        print("✅ Database is already perfectly healthy. No missing fatigue data found.")
        conn.close()
        return

    print(f"Found {total_games} games requiring fatigue backfills. Revving up the cache engine...\n")
    
    bulk_updates = []
    processed = 0

    for game_id, date_str, home, away in games:
        try:
            h_id = team_map.get(home)
            a_id = team_map.get(away)
            
            if not h_id or not a_id: 
                processed += 1
                continue
            
            # Use the newly cached functions
            h_fatigue = get_fatigue_cached(h_id, date_str)
            a_fatigue = get_fatigue_cached(a_id, date_str)
            
            # Queue the update into memory
            bulk_updates.append((h_fatigue, a_fatigue, game_id))
            processed += 1
            
            if processed % 25 == 0:
                print(f"   -> Processed {processed}/{total_games} games...")
                
        except Exception as e:
            processed += 1
            pass
            
    print("\n💾 Committing all updates to the database simultaneously...")
    
    # Bulk update the SQLite database in a fraction of a second
    cursor.executemany("""
        UPDATE game_logs 
        SET home_fatigue = ?, away_fatigue = ?, 
            home_lineup_mult = COALESCE(home_lineup_mult, 1.0), 
            away_lineup_mult = COALESCE(away_lineup_mult, 1.0)
        WHERE game_id = ?
    """, bulk_updates)
    
    conn.commit()
    conn.close()
    
    print(f"✅ Healing complete! {len(bulk_updates)} historical games updated securely.")

if __name__ == "__main__":
    heal_database()