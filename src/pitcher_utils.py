# -*- coding: utf-8 -*-
"""
Created on Tue May 12 20:22:42 2026

@author: jorda
"""

import requests

def get_pitcher_metrics(player_id):
    """Fetches 2026 season stats and calculates a FIP-based Pitcher Score."""
    if not player_id or player_id == "TBD":
        return {"score": 4.50, "era": "N/A", "whip": "N/A"} # League average default

    url = f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=season&group=pitching"
    
    try:
        response = requests.get(url, timeout=10).json()
        stats = response['stats'][0]['splits'][0]['stat']
        
        # 1. Extract raw components
        era = stats.get('earnedRunAverage', 4.50)
        whip = stats.get('whip', 1.30)
        hr = stats.get('homeRuns', 0)
        bb = stats.get('baseOnBalls', 0)
        hbp = stats.get('hitByPitch', 0)
        k = stats.get('strikeOuts', 0)
        ip = float(stats.get('inningsPitched', 1.0))
        
        # 2. Calculate FIP (Fielding Independent Pitching)
        # FIP Formula: ((13*HR) + (3*(BB+HBP)) - (2*K)) / IP + FIP_Constant
        # We use 3.2 as a standard 2026 constant to align with league ERA
        fip = ((13 * hr) + (3 * (bb + hbp)) - (2 * k)) / ip + 3.2
        
        # 3. Calculate a "Pitcher Score" (Weighted blend of ERA and FIP)
        # This acts as a more stable predictor than ERA alone
        pitcher_score = round((float(era) * 0.4) + (fip * 0.6), 2)
        
        return {
            "score": pitcher_score,
            "era": era,
            "whip": whip,
            "k_per_9": stats.get('strikeOutsPer9Inn', 0)
        }
    except Exception as e:
        print(f"Pitcher API Error ({player_id}): {e}")
        return {"score": 4.50, "era": "N/A", "whip": "N/A"}