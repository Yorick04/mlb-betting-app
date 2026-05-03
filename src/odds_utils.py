import os
import requests
from dotenv import load_dotenv

load_dotenv()

def get_mlb_odds():
    api_key = os.getenv("ODDS_API_KEY")
    if not api_key:
        print("Error: ODDS_API_KEY not found.")
        return {}

    # Fetching odds for MLB in the US market
    url = f"https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/?apiKey={api_key}&regions=us&markets=h2h,totals&oddsFormat=american"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        # If the API returns an error message instead of a list of games
        if isinstance(data, dict) and "message" in data:
            print(f"Odds API Error: {data['message']}")
            return {}

        odds_map = {}
        for game in data:
            home_team = game['home_team']
            ml_odds = "N/A"
            over_under = "N/A"
            
            for bookmaker in game.get('bookmakers', []):
                for market in bookmaker.get('markets', []):
                    # 1. Handle Money Line (h2h)
                    if market['key'] == 'h2h':
                        for outcome in market.get('outcomes', []):
                            if outcome['name'] == home_team:
                                ml_odds = outcome['price']
                    
                    # 2. Handle Totals (over_under)
                    elif market['key'] == 'totals':
                        # Outcomes is a list: [{'name': 'Over', 'price': -110, 'point': 8.5}, ...]
                        outcomes = market.get('outcomes', [])
                        if outcomes:
                            # We grab the 'point' from the first outcome (Over and Under share the same point)
                            over_under = outcomes[0].get('point', 'N/A')
            
            odds_map[home_team] = {"ML": ml_odds, "OU": over_under}
            
        return odds_map
    except Exception as e:
        print(f"Odds API critical failure: {e}")
        return {}