import pandas as pd
from pybaseball import statcast_pitcher_expected_stats
import re
import warnings

# Suppress pybaseball warnings for a clean console
warnings.filterwarnings('ignore')

# Cache to prevent hitting the API repeatedly during the same scraper run
_pitcher_cache = None

def _normalize_name(name):
    """Cleans names to ensure 'Kevin Gausman' matches 'Gausman, Kevin'"""
    if not name or pd.isna(name):
        return ""
    # Remove punctuation and lowercase
    name = re.sub(r'[^\w\s]', '', name.lower())
    # Split the name and sort alphabetically
    parts = name.split()
    return "".join(sorted(parts))

def load_statcast_data():
    global _pitcher_cache
    if _pitcher_cache is None:
        print("📊 Fetching fresh Expected Stats (xERA) from Baseball Savant...")
        try:
            # 2026 Season, minimum 50 batters faced
            df = statcast_pitcher_expected_stats(2026, 50)
            
            # --- THE FIX: Updated to handle PyBaseball's new 2026 column names ---
            if 'last_name, first_name' in df.columns:
                df['match_name'] = df['last_name, first_name'].astype(str)
            elif 'first_name' in df.columns and 'last_name' in df.columns:
                df['match_name'] = df['first_name'].astype(str) + " " + df['last_name'].astype(str)
            elif 'player_name' in df.columns:
                df['match_name'] = df['player_name'].astype(str)
            else:
                print(f"⚠️ PyBaseball Columns changed. Available columns: {list(df.columns)}")
                _pitcher_cache = pd.DataFrame()
                return

            df['match_name'] = df['match_name'].apply(_normalize_name)
            _pitcher_cache = df
            print("✅ Statcast xStats loaded successfully.")
        except Exception as e:
            print(f"⚠️ Could not fetch Statcast data: {e}")
            _pitcher_cache = pd.DataFrame()

def get_pitcher_xera(pitcher_name):
    """Returns the xERA for a given pitcher, or None if not found."""
    # This will use the cache if already loaded
    load_statcast_data()
    
    if _pitcher_cache is None or _pitcher_cache.empty or not pitcher_name:
        return None
        
    clean_target = _normalize_name(pitcher_name)
    match = _pitcher_cache[_pitcher_cache['match_name'] == clean_target]
    
    if not match.empty:
        # --- THE FIX: Updated 'est_era' to 'xera' based on the API output ---
        return match.iloc[0].get('xera', None)
    
    return None

def get_lineup_xba(team_name):
    """Placeholder for daily lineup xBA."""
    return None

def get_lineup_xslg(team_name):
    """Placeholder for daily lineup xSLG."""
    return None