import os, requests, pytz
from dotenv import load_dotenv
from datetime import datetime

load_dotenv(override=True)

# Dictionary to standardize Odds API / DraftKings names to match MLB Stats API exactly
TEAM_MAP = {
    "Oakland Athletics": "Athletics",
    "Sacramento Athletics": "Athletics",  # Failsafe for 2026 stadium shifts
    "St Louis Cardinals": "St. Louis Cardinals", # Fixes the missing period
    "LA Dodgers": "Los Angeles Dodgers",
    "LA Angels": "Los Angeles Angels",
    "NY Yankees": "New York Yankees",
    "NY Mets": "New York Mets"
}

def get_mlb_odds():
    api_key = os.getenv("ODDS_API_KEY")
    url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds"
    params = {'apiKey': api_key, 'regions': 'us', 'markets': 'h2h,totals', 'bookmakers': 'draftkings', 'oddsFormat': 'american'}
    
    try:
        data = requests.get(url, params=params).json()
        odds_dict = {}
        for game in data:
            # 1. Standardize the team names using the dictionary before building the key
            home = TEAM_MAP.get(game['home_team'], game['home_team'])
            away = TEAM_MAP.get(game['away_team'], game['away_team'])
            
            comm_utc = datetime.strptime(game['commence_time'], "%Y-%m-%dT%H:%M:%SZ")
            comm_ct = comm_utc.replace(tzinfo=pytz.utc).astimezone(pytz.timezone('US/Central'))
            key = f"{comm_ct.strftime('%Y-%m-%d')}_{home}_{away}"
            
            ml, total = "N/A", "N/A"
            for book in game.get('bookmakers', []):
                for market in book.get('markets', []):
                    if market['key'] == 'h2h':
                        # 2. Ensure we check the outcome name against the mapping too
                        ml = next((o['price'] for o in market['outcomes'] if TEAM_MAP.get(o['name'], o['name']) == home), "N/A")
                    elif market['key'] == 'totals':
                        total = market['outcomes'][0].get('point', 'N/A')
            odds_dict[key] = {'ml': ml, 'total': total, 'book': 'DraftKings'}
        return odds_dict
    except Exception as e:
        print(f"Error fetching odds: {e}")
        return {}