import pandas as pd
import re
import warnings
from datetime import datetime, timedelta
from pybaseball import statcast_pitcher_expected_stats, statcast

warnings.filterwarnings('ignore')

_pitcher_cache = None
_pitcher_gb_cache = None

def _normalize_name(name):
    if not name or pd.isna(name): return ""
    name = re.sub(r'[^\w\s]', '', name.lower())
    parts = name.split()
    return "".join(sorted(parts))

def load_statcast_data():
    global _pitcher_cache, _pitcher_gb_cache
    
    # 1. Fetch Savant Expected Stats (xERA)
    if _pitcher_cache is None:
        print("📊 Fetching Expected Stats (xERA) from Savant API...")
        try:
            df = statcast_pitcher_expected_stats(datetime.now().year, 50)
            df['match_name'] = df.get('player_name', df.get('last_name, first_name', '')).astype(str).apply(_normalize_name)
            _pitcher_cache = df
        except Exception as e:
            print(f"⚠️ Savant xERA Error: {e}")
            _pitcher_cache = pd.DataFrame()

    # 2. Compute Rolling 30-Day GB% from RAW Savant Physics Data
    if _pitcher_gb_cache is None:
        print("📊 Calculating rolling 30-day GB% directly from raw pitch physics...")
        try:
            end_dt = datetime.now()
            start_dt = end_dt - timedelta(days=30)
            
            # Fetch raw pitch data for the last 30 days (Official MLB API)
            pitch_df = statcast(start_dt=start_dt.strftime('%Y-%m-%d'), end_dt=end_dt.strftime('%Y-%m-%d'))
            
            # Filter for balls actually put in play (ignore strikeouts, walks, fouls)
            bip_df = pitch_df.dropna(subset=['bb_type'])
            
            # Group by pitcher and count total batted balls vs ground balls
            gb_counts = bip_df[bip_df['bb_type'] == 'ground_ball'].groupby('pitcher').size()
            total_bip = bip_df.groupby('pitcher').size()
            
            # Create a clean DataFrame for the math
            gb_df = pd.DataFrame({
                'ground_balls': gb_counts,
                'total_bip': total_bip
            }).fillna(0)
            
            # The Math: Ground Balls / Total Balls in Play
            gb_df['GB%'] = gb_df['ground_balls'] / gb_df['total_bip']
            
            # Map the pitcher IDs to their actual names for our lookup
            name_map = bip_df[['pitcher', 'player_name']].drop_duplicates().set_index('pitcher')['player_name']
            gb_df['player_name'] = gb_df.index.map(name_map)
            
            # Normalize names to match your scraper format (e.g., "Joey Gallo")
            gb_df['match_name'] = gb_df['player_name'].astype(str).apply(lambda x: _normalize_name(' '.join(reversed(x.split(', ')))) if ',' in x else _normalize_name(x))
            
            _pitcher_gb_cache = gb_df.reset_index()
            print("✅ 30-Day Rolling GB% calculated and cached successfully.")
            
        except Exception as e:
            print(f"⚠️ Savant GB% calculation failed: {e}. Defaulting to league average 0.43.")
            _pitcher_gb_cache = pd.DataFrame()

def get_pitcher_gb_pct(pitcher_name):
    load_statcast_data()
    league_avg = 0.43
    if _pitcher_gb_cache is None or _pitcher_gb_cache.empty: return league_avg
    
    match = _pitcher_gb_cache[_pitcher_gb_cache['match_name'] == _normalize_name(pitcher_name)]
    if not match.empty:
        # Ignore pitchers with less than 5 balls in play in the last month (use league average)
        if match.iloc[0]['total_bip'] < 5:
            return league_avg
        val = match.iloc[0]['GB%']
        return float(val) if not pd.isna(val) else league_avg
    return league_avg

def get_pitcher_xera(pitcher_name):
    load_statcast_data()
    if _pitcher_cache is None or _pitcher_cache.empty: return None
    match = _pitcher_cache[_pitcher_cache['match_name'] == _normalize_name(pitcher_name)]
    return match.iloc[0].get('xera') if not match.empty else None