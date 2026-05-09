import os
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

def get_mlb_odds():
    api_key = os.getenv("ODDS_API_KEY")
    
    if not api_key:
        print("❌ ERROR: No ODDS_API_KEY found.")
        return {}
    else:
        print(f"📡 Using API Key: {api_key[:4]}...{api_key[-4:]}")

    # Official V4 Endpoint
    base_url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds"
    
    params = {
        'apiKey': api_key,
        'regions': 'us',
        'markets': 'h2h,totals',
        'bookmakers': 'draftkings',
        'oddsFormat': 'american'
    }
    
    try:
        response = requests.get(base_url, params=params, timeout=15)
        
        if response.status_code != 200:
            print(f"❌ API SERVER ERROR {response.status_code}: {response.text}")
            return {}

        data = response.json()
        
        print("\n" + "="*50)
        print("DEBUG: GAMES CURRENTLY IN THE ODDS API")
        print("="*50)
        
        odds_dict = {}
        for game in data:
            home = game['home_team']
            away = game['away_team']
            print(f"-> {away} @ {home}")
            
            key = f"{home}_{away}"
            
            ml, total = "N/A", "N/A"
            for book in game.get('bookmakers', []):
                if book['key'] == 'draftkings':
                    for market in book.get('markets', []):
                        if market['key'] == 'h2h':
                            for outcome in market['outcomes']:
                                if outcome['name'] == home:
                                    ml = outcome['price']
                        elif market['key'] == 'totals':
                            outcomes = market.get('outcomes', [])
                            if outcomes:
                                total = outcomes[0].get('point', 'N/A')
            
            odds_dict[key] = {'ml': ml, 'total': total, 'book': 'DraftKings'}
        
        print("="*50 + "\n")
        return odds_dict

    except Exception as e:
        print(f"❌ CRITICAL ERROR in odds_utils: {e}")
        return {}