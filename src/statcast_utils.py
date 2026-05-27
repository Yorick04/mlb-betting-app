import pandas as pd
import requests
import io
import re
import warnings
from pybaseball import statcast_pitcher_expected_stats, pitching_stats

warnings.filterwarnings('ignore')

_pitcher_cache = None
_pitcher_batted_ball_cache = None

def _normalize_name(name):
    if not name or pd.isna(name): return ""
    name = re.sub(r'[^\w\s]', '', name.lower())
    parts = name.split()
    return "".join(sorted(parts))

def load_statcast_data():
    global _pitcher_cache, _pitcher_batted_ball_cache
    
    # 1. Fetch Savant Data
    if _pitcher_cache is None:
        print("📊 Fetching fresh Expected Stats (xERA)...")
        try:
            df = statcast_pitcher_expected_stats(2026, 50)
            df['match_name'] = df.get('player_name', df.get('last_name, first_name', '')).astype(str).apply(_normalize_name)
            _pitcher_cache = df
        except: _pitcher_cache = pd.DataFrame()

    # 2. Fetch FanGraphs Data with Fail-Safe
    if _pitcher_batted_ball_cache is None:
        print("📊 Fetching fresh GB% from FanGraphs...")
        try:
            # Browser spoofing to avoid 403 Forbidden
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}
            url = "https://www.fangraphs.com/leaders.aspx?pos=all&stats=pit&lg=all&qual=10&type=2&season=2026&month=0&season1=2026&ind=0&team=0,ts&rost=0&age=0&filter=&players=0&sort=23,d"
            response = requests.get(url, headers=headers)
            dfs = pd.read_html(io.StringIO(response.text))
            fg_df = dfs[16]
            fg_df['match_name'] = fg_df['Name'].apply(_normalize_name)
            _pitcher_batted_ball_cache = fg_df
            print("✅ FanGraphs GB% loaded successfully.")
        except Exception as e:
            print(f"⚠️ FanGraphs Access Denied: {e}. Defaulting to 0.43.")
            _pitcher_batted_ball_cache = pd.DataFrame()

def get_pitcher_gb_pct(pitcher_name):
    load_statcast_data()
    league_avg = 0.43
    if _pitcher_batted_ball_cache is None or _pitcher_batted_ball_cache.empty: return league_avg
    match = _pitcher_batted_ball_cache[_pitcher_batted_ball_cache['match_name'] == _normalize_name(pitcher_name)]
    if not match.empty:
        val = match.iloc[0].get('GB%', league_avg)
        try: return float(str(val).replace('%', '')) / 100.0 if '%' in str(val) else float(val)
        except: return league_avg
    return league_avg

def get_pitcher_xera(pitcher_name):
    load_statcast_data()
    if _pitcher_cache is None or _pitcher_cache.empty: return None
    match = _pitcher_cache[_pitcher_cache['match_name'] == _normalize_name(pitcher_name)]
    return match.iloc[0].get('xera') if not match.empty else None