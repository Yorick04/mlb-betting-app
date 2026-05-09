import os
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

def get_mlb_odds():
    api_key = os.getenv("ODDS_API_KEY")
    if not api_key:
        return {}

    # Added &bookmakers=draftkings to ensure we only get DK lines
    url = f"https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/?apiKey={api_key}&regions=us&markets=h2h,totals&bookmakers=draftkings&oddsFormat=american"
    
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        odds_dict = {}

        for game in data:
            home_team = game['home_team'] 
            away_team = game['away_team']
            game_key = f"{home_team}_{away_team}"

            ml = "N/A"
            total = "N/A"
            book_name = "N/A"

            if game.get('bookmakers'):
                # Since we filtered the API, index 0 is guaranteed to be DraftKings
                bookmaker_info = game['bookmakers'][0]
                book_name = bookmaker_info.get('title', 'Unknown')
                
                markets = bookmaker_info.get('markets', [])
                for market in markets:
                    if market['key'] == 'h2h':
                        for outcome in market['outcomes']:
                            if outcome['name'] == home_team:
                                ml = outcome['price']
                    elif market['key'] == 'totals':
                        for outcome in market['outcomes']:
                            if outcome['name'] == 'Over':
                                total = outcome.get('point', "N/A")

            odds_dict[game_key] = {"ml": ml, "total": total, "book": book_name}
        
        return odds_dict

    except Exception as e:
        print(f"Error fetching odds: {e}")
        return {}