import os
import requests
import pytz
import json
from dotenv import load_dotenv
from datetime import datetime, timedelta
import db_manager

load_dotenv(override=True)

session = requests.Session()

# Expanded to ensure all 30 teams map perfectly, including both NY and Chicago teams
TEAM_MAP = {
    "Oakland Athletics": "Athletics", "Sacramento Athletics": "Athletics", "Oakland A's": "Athletics",
    "St Louis Cardinals": "St. Louis Cardinals", "St. Louis Cardinals": "St. Louis Cardinals",
    "LA Dodgers": "Los Angeles Dodgers", "LA Angels": "Los Angeles Angels",
    "NY Yankees": "New York Yankees", "New York Yankees": "New York Yankees",
    "NY Mets": "New York Mets", "New York Mets": "New York Mets",
    "Chicago Cubs": "Chicago Cubs", "Chicago White Sox": "Chicago White Sox",
    "Arizona D-backs": "Arizona Diamondbacks", "Arizona Diamondbacks": "Arizona Diamondbacks",
    "Atlanta Braves": "Atlanta Braves"
}

def get_mlb_odds():
    now_utc = datetime.now(pytz.utc)
    today_ct_str = now_utc.astimezone(pytz.timezone('US/Central')).strftime('%Y-%m-%d')
    cache_filename = f"odds_cache_{today_ct_str}.json"

    # --- 1. Caching Layer to Protect API Quota ---
    if os.path.exists(cache_filename):
        print(f"📦 Loading DraftKings odds from local cache: {cache_filename}")
        with open(cache_filename, 'r') as file:
            return json.load(file)

    print("🌐 Fetching fresh odds from API...")
    api_key = os.getenv("ODDS_API_KEY")
    url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds"
    params = {
        'apiKey': api_key, 
        'regions': 'us', 
        'markets': 'h2h,totals,spreads', 
        'bookmakers': 'draftkings', 
        'oddsFormat': 'american'
    }
    
    try:
        response = session.get(url, params=params)
        
        if response.status_code == 429:
            print("❌ Rate limited by API (429). Out of pulls.")
            return {}
        elif response.status_code != 200:
            print(f"❌ API Error: {response.status_code}")
            return {}

        data = response.json()
        odds_dict = {}
        
        for game in data:
            comm_utc = datetime.strptime(game['commence_time'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.utc)
            comm_ct = comm_utc.astimezone(pytz.timezone('US/Central'))
            date_str = comm_ct.strftime('%Y-%m-%d')
            
            # Strict lockout: Discard mismatched dates and games that went live more than 5 minutes ago
            if date_str != today_ct_str:
                continue 
                
            if now_utc > (comm_utc + timedelta(minutes=5)):
                continue 
                
            home = TEAM_MAP.get(game['home_team'], game['home_team'])
            away = TEAM_MAP.get(game['away_team'], game['away_team'])
            
            # --- 2. CRITICAL FIX: Match the scraper.py lookup key ---
            key = f"{home}_{away}"
            db_id = db_manager.generate_game_id(date_str, home, away)
            
            odds_data = {
                'game_id': db_id,
                'game_date': date_str,
                'home_team': home,
                'away_team': away,
                'ml_home': "N/A", 'ml_away': "N/A", 'total': "N/A", 'ou_total': "N/A", 'spread': "N/A",
                'rl_home_point': "N/A", 'rl_home_price': "N/A",
                'rl_away_point': "N/A", 'rl_away_price': "N/A",
                'book': 'DraftKings'
            }
            
            for book in game.get('bookmakers', []):
                for market in book.get('markets', []):
                    if market['key'] == 'h2h':
                        odds_data['ml_home'] = next((o['price'] for o in market['outcomes'] if TEAM_MAP.get(o['name'], o['name']) == home), "N/A")
                        odds_data['ml_away'] = next((o['price'] for o in market['outcomes'] if TEAM_MAP.get(o['name'], o['name']) == away), "N/A")
                    elif market['key'] == 'totals':
                        point = market['outcomes'][0].get('point', 'N/A')
                        odds_data['total'] = point
                        odds_data['ou_total'] = point
                    elif market['key'] == 'spreads':
                        # Final transformation: Lock onto the standard +/- 1.5 runline to reject wild alternate spreads
                        standard_outcomes = [o for o in market['outcomes'] if abs(float(o.get('point', 0))) == 1.5]
                        target_outcomes = standard_outcomes if standard_outcomes else market['outcomes']
                        
                        for o in target_outcomes:
                            if TEAM_MAP.get(o['name'], o['name']) == home:
                                odds_data['rl_home_point'] = o.get('point', "N/A")
                                odds_data['rl_home_price'] = o.get('price', "N/A")
                                odds_data['spread'] = o.get('point', "N/A")
                            else:
                                odds_data['rl_away_point'] = o.get('point', "N/A")
                                odds_data['rl_away_price'] = o.get('price', "N/A")

            odds_dict[key] = odds_data
        
        # --- 3. Save parsed odds to cache file to protect quota ---
        if odds_dict:
            with open(cache_filename, 'w') as file:
                json.dump(odds_dict, file)
            print("✅ Odds successfully cached for today.")

        return odds_dict
        
    except Exception as e:
        print(f"Error fetching odds: {e}")
        return {}