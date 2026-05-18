import os, requests, pytz
from dotenv import load_dotenv
from datetime import datetime

load_dotenv(override=True)

# Standardized session for faster, reused API connections
session = requests.Session()

TEAM_MAP = {
    "Oakland Athletics": "Athletics", "Sacramento Athletics": "Athletics", "Oakland A's": "Athletics",
    "St Louis Cardinals": "St. Louis Cardinals", "St. Louis Cardinals": "St. Louis Cardinals",
    "LA Dodgers": "Los Angeles Dodgers", "LA Angels": "Los Angeles Angels",
    "NY Yankees": "New York Yankees", "NY Mets": "New York Mets",
    "Arizona D-backs": "Arizona Diamondbacks", "Arizona Diamondbacks": "Arizona Diamondbacks"
}

def get_mlb_odds():
    api_key = os.getenv("ODDS_API_KEY")
    url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds"
    # Added 'spreads' to markets
    params = {'apiKey': api_key, 'regions': 'us', 'markets': 'h2h,totals,spreads', 'bookmakers': 'draftkings', 'oddsFormat': 'american'}
    
    try:
        data = session.get(url, params=params).json()
        odds_dict = {}
        for game in data:
            home = TEAM_MAP.get(game['home_team'], game['home_team'])
            away = TEAM_MAP.get(game['away_team'], game['away_team'])
            
            comm_utc = datetime.strptime(game['commence_time'], "%Y-%m-%dT%H:%M:%SZ")
            comm_ct = comm_utc.replace(tzinfo=pytz.utc).astimezone(pytz.timezone('US/Central'))
            key = f"{comm_ct.strftime('%Y-%m-%d')}_{home}_{away}"
            
            odds_data = {
                'ml_home': "N/A", 'ml_away': "N/A", 'total': "N/A",
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
                        odds_data['total'] = market['outcomes'][0].get('point', 'N/A')
                    elif market['key'] == 'spreads':
                        # Grab run line data
                        for o in market['outcomes']:
                            if TEAM_MAP.get(o['name'], o['name']) == home:
                                odds_data['rl_home_point'] = o.get('point', "N/A")
                                odds_data['rl_home_price'] = o.get('price', "N/A")
                            else:
                                odds_data['rl_away_point'] = o.get('point', "N/A")
                                odds_data['rl_away_price'] = o.get('price', "N/A")

            odds_dict[key] = odds_data
        return odds_dict
    except Exception as e:
        print(f"Error fetching odds: {e}")
        return {}