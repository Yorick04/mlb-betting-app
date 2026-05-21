import requests
from datetime import datetime, timedelta
import pytz

session = requests.Session()

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
    """Optimized: Fetches games from the 3 days prior to the given game date."""
    tz = pytz.timezone('US/Central')
    
    if game_date_str:
        # If a date is provided (like during historical scraping), use it
        game_date = datetime.strptime(game_date_str, '%Y-%m-%d').replace(tzinfo=tz)
    else:
        # Fallback to today for live daily scraping
        game_date = datetime.now(tz)
        
    start_date = (game_date - timedelta(days=3)).strftime('%Y-%m-%d')
    end_date = (game_date - timedelta(days=1)).strftime('%Y-%m-%d')
    
    fatigue_penalty = 0.0
    
    url = f"https://statsapi.mlb.com/api/v1/schedule/games/?sportId=1&teamId={team_id}&startDate={start_date}&endDate={end_date}&hydrate=team,boxscore"
    try:
        resp = session.get(url, timeout=10).json()
        for date_obj in resp.get('dates', []):
            for game in date_obj.get('games', []):
                is_home = (game['teams']['home']['team']['id'] == team_id)
                try:
                    pitchers = game['boxscore']['teams']['home']['pitchers'] if is_home else game['boxscore']['teams']['away']['pitchers']
                    if len(pitchers) > 5:
                        fatigue_penalty += 0.15
                except KeyError:
                    pass
    except Exception:
        pass
        
    return round(fatigue_penalty, 2)