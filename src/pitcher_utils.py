import requests
from functools import lru_cache

# Initialize a persistent session to prevent GitHub Actions timeouts
session = requests.Session()

# 2026 League Average FIP Constant (Can be updated dynamically mid-season)
CURRENT_FIP_CONSTANT = 3.20

@lru_cache(maxsize=128)
def get_pitcher_metrics(player_id):
    """
    Fetches 2026 season stats and calculates a FIP-based Pitcher Score.
    Includes robust fallbacks for rookies and unrated players.
    """
    # Standard 2026 baseline defaults (League average)
    default_metrics = {
        "score": 4.50, 
        "era": "N/A", 
        "whip": "N/A", 
        "k_per_9": 0
    }

    if not player_id or player_id == "TBD":
        return default_metrics

    url = f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=season&group=pitching"
    
    try:
        # Replaced requests.get with session.get
        response = session.get(url, timeout=10).json()
        
        # CRITICAL SAFETY CHECK: Ensure stats, splits, and the inner dictionary exist
        if (
            "stats" in response 
            and response["stats"] 
            and "splits" in response["stats"][0] 
            and response["stats"][0]["splits"]
        ):
            stats = response['stats'][0]['splits'][0]['stat']
        else:
            # Safely handle rookies/call-ups with no major league data yet
            return default_metrics
        
        # 1. Extract raw components with defaults
        era = stats.get('earnedRunAverage', 4.50)
        whip = stats.get('whip', 1.30)
        hr = stats.get('homeRuns', 0)
        bb = stats.get('baseOnBalls', 0)
        hbp = stats.get('hitByPitch', 0)
        k = stats.get('strikeOuts', 0)
        
        # Safely parse Innings Pitched to avoid division by zero
        try:
            ip = float(stats.get('inningsPitched', 1.0))
        except (ValueError, TypeError):
            ip = 1.0
            
        if ip <= 0.0:
            ip = 1.0
        
        # 2. Calculate FIP (Fielding Independent Pitching)
        # FIP Formula: ((13*HR) + (3*(BB+HBP)) - (2*K)) / IP + FIP_Constant
        fip = ((13 * hr) + (3 * (bb + hbp)) - (2 * k)) / ip + CURRENT_FIP_CONSTANT
        
        # 3. Calculate a "Pitcher Score" (Weighted blend: 40% ERA / 60% FIP)
        pitcher_score = round((float(era) * 0.4) + (fip * 0.6), 2)
        
        return {
            "score": pitcher_score,
            "era": era,
            "whip": whip,
            "k_per_9": stats.get('strikeOutsPer9Inn', 0)
        }
        
    except Exception as e:
        print(f"Pitcher API Error ({player_id}): {e}")
        return default_metrics