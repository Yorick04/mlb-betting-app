import os, requests, pytz
from dotenv import load_dotenv
from datetime import datetime

load_dotenv(override=True)

def get_mlb_odds():
    api_key = os.getenv("ODDS_API_KEY")
    url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds"
    params = {'apiKey': api_key, 'regions': 'us', 'markets': 'h2h,totals', 'bookmakers': 'draftkings', 'oddsFormat': 'american'}
    
    try:
        data = requests.get(url, params=params).json()
        odds_dict = {}
        for game in data:
            home, away = game['home_team'], game['away_team']
            comm_utc = datetime.strptime(game['commence_time'], "%Y-%m-%dT%H:%M:%SZ")
            comm_ct = comm_utc.replace(tzinfo=pytz.utc).astimezone(pytz.timezone('US/Central'))
            key = f"{comm_ct.strftime('%Y-%m-%d')}_{home}_{away}"
            
            ml, total = "N/A", "N/A"
            for book in game.get('bookmakers', []):
                for market in book.get('markets', []):
                    if market['key'] == 'h2h':
                        ml = next((o['price'] for o in market['outcomes'] if o['name'] == home), "N/A")
                    elif market['key'] == 'totals':
                        total = market['outcomes'][0].get('point', 'N/A')
            odds_dict[key] = {'ml': ml, 'total': total, 'book': 'DraftKings'}
        return odds_dict
    except: return {}