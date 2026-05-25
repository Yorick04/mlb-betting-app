import sqlite3
import pandas as pd

def audit_residuals():
    conn = sqlite3.connect("mlb_historical_data.db")
    
    # Query to get predictions and actuals
    query = """
    SELECT 
        game_date, 
        home_team, 
        away_team, 
        ou_total, 
        actual_home_score + actual_away_score as actual_total,
        umpire_multiplier -- Assuming you logged this
    FROM game_logs 
    WHERE status = 'FINAL' AND ou_total IS NOT NULL
    """
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    # Calculate Residual: (Predicted - Actual)
    df['ou_total'] = pd.to_numeric(df['ou_total'])
    df['residual'] = df['ou_total'] - df['actual_total']
    
    # Analyze by Umpire (if you have umpire names logged)
    # If not logged, you can group by stadium/park_factor to see similar trends
    print("--- Top 10 Umpire/Condition Residuals (High Error) ---")
    
    # Shows the average error per game
    worst_performers = df.groupby('umpire_multiplier')['residual'].agg(['mean', 'count']).sort_values(by='mean', ascending=False)
    print(worst_performers.head(10))

if __name__ == "__main__":
    audit_residuals()