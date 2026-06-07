import requests
from datetime import datetime, timedelta
import pytz

session = requests.Session()

# The Memory Caches to prevent downloading the same boxscores repeatedly
SCHEDULE_CACHE = {}
BOXSCORE_CACHE = {}

def get_bullpen_metrics(team_id):
    url = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/stats?stats=season&group=pitching&statType=relief"
    try:
        response = session.get(url, timeout=10).json()
        stats = response['stats'][0]['splits'][0]['stat']
        era = float(stats.get('earnedRunAverage', 4.20))
        whip = float(stats.get('whip', 1.35))
        bp_score = round((era * 0.5) + (whip * 2.5), 2)
        return {"bp_score": bp_score, "era": era, "whip": whip}
    except:
        return {"bp_score": 4.50, "era": 4.20, "whip": 1.35}

def get_bullpen_fatigue(team_id, game_date_str=None):
    """Optimized: Fetches games from the 3 days prior, using memory caches to prevent API timeouts."""
    tz = pytz.timezone('US/Central')
    
    if game_date_str:
        game_date = datetime.strptime(game_date_str, '%Y-%m-%d').replace(tzinfo=tz)
    else:
        game_date = datetime.now(tz)
        
    start_date = (game_date - timedelta(days=3)).strftime('%Y-%m-%d')
    end_date = (game_date - timedelta(days=1)).strftime('%Y-%m-%d')
    
    fatigue_penalty = 0.0
    
    # Step 1: Get the Schedule for the last 3 days
    sched_key = f"{team_id}_{start_date}_{end_date}"
    if sched_key in SCHEDULE_CACHE:
        resp = SCHEDULE_CACHE[sched_key]
    else:
        schedule_url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&teamId={team_id}&startDate={start_date}&endDate={end_date}"
        try:
            resp = session.get(schedule_url, timeout=10).json()
            SCHEDULE_CACHE[sched_key] = resp
        except Exception:
            return 0.0

    for date_obj in resp.get('dates', []):
        for game in date_obj.get('games', []):
            game_pk = game.get('gamePk')
            if not game_pk:
                continue
                
            is_home = (game['teams']['home']['team']['id'] == team_id)
            team_side = 'home' if is_home else 'away'
            
            # Step 2: Check the Boxscore Cache before hitting the API
            if game_pk in BOXSCORE_CACHE:
                box_resp = BOXSCORE_CACHE[game_pk]
            else:
                box_url = f"https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore"
                try:
                    box_resp = session.get(box_url, timeout=10).json()
                    BOXSCORE_CACHE[game_pk] = box_resp
                except Exception:
                    continue
            
            # Count how many pitchers the team used that game
            try:
                pitchers = box_resp['teams'][team_side].get('pitchers', [])
                if len(pitchers) > 5:
                    fatigue_penalty += 0.15
            except Exception:
                pass
                
    return round(fatigue_penalty, 2)