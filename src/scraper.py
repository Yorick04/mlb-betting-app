import pybaseball as pb
from datetime import datetime

def get_todays_slate():
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        # The updated way to get today's matchups
        # Note: 'schedule' returns a DataFrame of the season; we filter for today
        year = datetime.now().year
        data = pb.schedule_and_record(year, "ATL") # Example for one team
        # To get the WHOLE league schedule correctly in 2026:
        from pybaseball import amateur_draft # Just an example of the import style
        
        # ACTUALLY - Let's use the most reliable method for daily matchups:
        from pybaseball import statcast
        # We search for a tiny window to see who is playing
        print(f"Fetching games for {today}...")
        
        # Professional fallback: If pybaseball schedule is buggy, we'd usually 
        # use a direct MLB API call. For now, try this:
        # schedule = pb.mlb_schedule(today) 
        
        # FIX: Many pros use the internal 'mlb_schedule' function:
        from pybaseball.mlb_schedule import mlb_schedule
        sched = mlb_schedule(today)
        return sched

    except Exception as e:
        print(f"Error: {e}")
        return None