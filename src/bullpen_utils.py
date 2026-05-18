import requests
from datetime import datetime, timedelta
import pytz

def get_bullpen_metrics(team_id):
    """Fetches 2026 team relief stats and calculates a Bullpen Score."""
    # statType=relief isolates the bullpen from the starters in the MLB API
    url = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/stats?stats=season&group=pitching&statType=relief"
    
    try:
        response = requests.get(url, timeout=10).json()
        stats = response['stats'][0]['splits'][0]['stat']
        
        era = float(stats.get('earnedRunAverage', 4.20))
        whip = float(stats.get('whip', 1.35))
        
        # Bullpen Score: Blend of ERA and WHIP (heavily favoring WHIP for volatility)
        bp_score = round((era * 0.5) + (whip * 2.5), 2)
        return {"bp_score": bp_score, "era": era, "whip": whip}
    except:
        return {"bp_score": 4.50, "era": 4.20, "whip": 1.35}

def get_bullpen_fatigue(team_id):
    """Checks the last 3 days of box scores for reliever workload."""
    tz = pytz.timezone('US/Central')
    today = datetime.now(tz)
    fatigue_penalty = 0.0
    
    # Check last 3 days
    for i in range(1, 4):
        date_str = (today - timedelta(days=i)).strftime('%Y-%m-%d')
        url = f"https://statsapi.mlb.com/api/v1/schedule/games/?sportId=1&teamId={team_id}&date={date_str}"
        try:
            resp = requests.get(url).json()
            games = resp.get('dates', [{}])[0].get('games', [])
            for game in games:
                game_pk = game['gamePk']
                # Fetch boxscore to see who pitched
                box = requests.get(f"https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore").json()
                pitchers = box['teams']['home']['pitchers'] if game['teams']['home']['team']['id'] == team_id else box['teams']['away']['pitchers']
                
                # If the team used 5+ relievers in a single game, add fatigue
                if len(pitchers) > 5:
                    fatigue_penalty += 0.15
        except: continue
        
    return round(fatigue_penalty, 2)