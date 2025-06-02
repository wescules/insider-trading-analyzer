import os
import sqlite3

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
DB_PATH = os.path.join(DATA_DIR, 'insider_trading.db')
conn = sqlite3.connect(DB_PATH)

# Buyers with No 10b5-1 Plans (Unplanned Trades)
# officers only
# buying in a 5 day window
# insider threshold is 2
def cluster_buys_query(min_insiders=2, window_days=5, transaction_type='P'):
    query = """
        SELECT 
            f1.issuer_ticker AS ticker,
            f1.transaction_date,
            COUNT(DISTINCT f1.reporting_owner) AS insider_count,
            SUM(CAST(f1.transaction_shares AS REAL)) AS total_shares,
            SUM(CAST(f1.transaction_shares AS REAL) * CAST(f1.transaction_price AS REAL)) AS total_value
        FROM insider_trading f1
        JOIN insider_trading f2
            ON f1.issuer_ticker = f2.issuer_ticker
        AND f1.transaction_type = ?
        AND f2.transaction_type = ?
        AND ABS(julianday(f1.transaction_date) - julianday(f2.transaction_date)) <= ?
        WHERE f1.reporting_owner_position IS NOT NULL AND f1.reporting_owner_position != ''
        AND (f1.aff10b5One IS NULL OR f1.aff10b5One = '' OR f1.aff10b5One = 'false' OR f1.aff10b5One = '0')
        GROUP BY f1.issuer_ticker, f1.transaction_date
        HAVING insider_count >= ?
        ORDER BY insider_count;
        """
    return query, (transaction_type, transaction_type, window_days, min_insiders)

def big_money_query(dollar_value=500000, transaction_type='P'):
    query = """
            SELECT 
                issuer_ticker,
                transaction_date,
                reporting_owner,
                reporting_owner_position,
                CAST(transaction_shares AS REAL) * CAST(transaction_price AS REAL) AS dollar_value
            FROM insider_trading
            WHERE transaction_type = ?
            AND dollar_value >= ?
            ORDER BY dollar_value ASC
        """
    return query, (transaction_type, dollar_value)

def repeated_buyer_query(buy_count_threshhold=3, transaction_type='P'):
    query = """
        SELECT issuer_ticker, reporting_owner, COUNT(*) AS buy_count
        FROM insider_trading
        WHERE transaction_type = ?
        GROUP BY issuer_ticker, reporting_owner
        HAVING buy_count >= ?
        ORDER BY buy_count ASC
        """
    return query, (transaction_type, buy_count_threshhold)

 # Shows insiders buying repeatedly — potential long-term belief in the stock. (Accumulation)
def find_repeated_buyer_purchases():
    cursor = conn.cursor()
    
    query, params = repeated_buyer_query()
    
    results = cursor.execute(query, params).fetchall()

    for row in results:
        print(f"Ticker: https://finviz.com/quote.ashx?t={row[0]}, Owner: {row[1]}, buy_count: {row[2]}")

# Detect large personal investments — more likely to be conviction-based.
def find_large_purchases():
    cursor = conn.cursor()
    
    query, params = big_money_query()
    
    results = cursor.execute(query, params).fetchall()

    for row in results:
        print(f"Ticker: https://finviz.com/quote.ashx?t={row[0]}, Date: {row[1]}, Owner: {row[2]}, Position: {row[3]}, Value: ${row[4]}")

# Cluster Buys (Multiple Insiders in a Short Time Window)
def find_cluster_buys():
    cursor = conn.cursor()
    
    query, params = cluster_buys_query()
    results = cursor.execute(query, params).fetchall()

    for row in results:
        print(f"Ticker: https://finviz.com/quote.ashx?t={row[0]}, Date: {row[1]}, Insiders: {row[2]}, Shares: {row[3]}, Value: ${row[4]}")

if __name__ == "__main__":
    # find_cluster_buys()
    # find_large_purchases()
    find_repeated_buyer_purchases()