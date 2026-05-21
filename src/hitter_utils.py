import requests
from functools import lru_cache

# 2026 League Average OPS Baseline
LEAGUE_AVG_OPS = 0.720

@lru_cache(maxsize=128)
def get_pitcher_hand(pitcher_id):
    """Hits the MLB API to determine if the opposing starter is a LHP or RHP."""
    if not pitcher_id or pitcher_id == "TBD": 
        return 'R' # Default to right-handed if TBD
        
    try:
        url = f"https://statsapi.mlb.com/api/v1/people/{pitcher_id}"
        resp = requests.get(url, timeout=10).json()
        return resp['people'][0]['pitchHand']['code']
    except:
        return 'R'

@lru_cache(maxsize=128)
def get_lineup_multiplier(team_id, opp_pitcher_id, game_date_str=None):
    pitcher_hand = get_pitcher_hand(opp_pitcher_id)
    
    # Dynamically extract the season from the game date
    season = "2026"
    if game_date_str:
        season = game_date_str[:4]
        
    url = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/stats?stats=statSplits&group=hitting&season={season}"
    
    try:
        response = requests.get(url, timeout=10).json()
        splits = response.get('stats', [{}])[0].get('splits', [])
        
        ops = LEAGUE_AVG_OPS
        for split in splits:
            desc = split.get('split', {}).get('description', '')
            # Use 'in' to catch variations like 'vs LHP' or 'vs. LHP'
            if (pitcher_hand == 'L' and 'LHP' in desc) or (pitcher_hand == 'R' and 'RHP' in desc):
                ops = float(split.get('stat', {}).get('ops', LEAGUE_AVG_OPS))
                break
        
        multiplier = ops / LEAGUE_AVG_OPS
        return round(min(max(multiplier, 0.80), 1.25), 3)
        
    except Exception as e:
        return 1.00 # Neutral fallback
    
def filter_valid_batters(roster_data):
    """
    Utility block for when you transition to individual player parsing. 
    Safely filters out pitchers and known non-batters from active rosters.
    """
    valid_batters = []
    for player in roster_data:
        name = player.get('person', {}).get('fullName', '')
        position = player.get('position', {}).get('abbreviation', 'P')
        
        # Exclude pitchers strictly instead of hardcoding names
        if position == 'P':
            continue
            
        valid_batters.append(player)
    return valid_batters