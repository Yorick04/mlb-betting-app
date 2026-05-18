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
def get_lineup_multiplier(team_id, opp_pitcher_id):
    """
    Calculates an offensive threat score by evaluating the team's 
    overall hitting stats against the specific handedness of the opposing pitcher.
    """
    pitcher_hand = get_pitcher_hand(opp_pitcher_id)
    
    # MLB API statGroup for 2026 hitting splits
    url = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/stats?stats=statSplits&group=hitting&season=2026"
    
    try:
        response = requests.get(url, timeout=10).json()
        splits = response.get('stats', [{}])[0].get('splits', [])
        
        target_desc = 'vs LHP' if pitcher_hand == 'L' else 'vs RHP'
        
        ops = LEAGUE_AVG_OPS
        for split in splits:
            if split.get('split', {}).get('description') == target_desc:
                ops = float(split.get('stat', {}).get('ops', LEAGUE_AVG_OPS))
                break
        
        # Create a multiplier (e.g., an .800 OPS = 1.11 multiplier)
        multiplier = ops / LEAGUE_AVG_OPS
        
        # Floor and ceiling the multiplier so small sample sizes don't break the model
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