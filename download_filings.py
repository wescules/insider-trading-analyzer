from datetime import datetime, timedelta
import argparse  # for --no download option command line argument
import pandas as pd
import os
import glob
import xml.etree.ElementTree as ET
import json
import sqlite3
import requests
import io
from sec_edgar_downloader import Downloader
import csv

# Use relative path for data directory
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
DB_PATH = os.path.join(DATA_DIR, 'insider_trading.db')
SP500_URL = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
SMALL_CAP_COMPANIES = os.path.join(DATA_DIR, "small_cap_companies.csv")

def get_small_cap_companies():
    """Fetch the list of small, micro and nano cap companies"""
    # Read the CSV into a DataFrame
    df = pd.read_csv(SMALL_CAP_COMPANIES)
    
    # Extract the ticker symbols (assuming the column is named 'Symbol')
    if 'Symbol' in df.columns:
        # Clean the ticker symbols (remove any special characters like dots)
        tickers = [ticker.replace('.', '-') for ticker in df['Symbol'].tolist()]
        print(f"Successfully fetched {len(tickers)} S&P 500 companies")
        return tickers
    else:
        print(f"Column 'Symbol' not found in CSV. Available columns: {df.columns.tolist()}")
        # Return a default list as fallback
        return ["AAPL", "MSFT", "AMZN", "GOOGL", "META"]

def get_sp500_companies():
    """Fetch the list of S&P 500 companies from GitHub."""
    try:
        print("Fetching S&P 500 companies list...")
        
        # Fetch the CSV data from the URL
        response = requests.get(SP500_URL)
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        # Read the CSV into a DataFrame
        df = pd.read_csv(io.StringIO(response.text))
        
        # Extract the ticker symbols (assuming the column is named 'Symbol')
        if 'Symbol' in df.columns:
            # Clean the ticker symbols (remove any special characters like dots)
            tickers = [ticker.replace('.', '-') for ticker in df['Symbol'].tolist()]
            print(f"Successfully fetched {len(tickers)} S&P 500 companies")
            return tickers
        else:
            print(f"Column 'Symbol' not found in CSV. Available columns: {df.columns.tolist()}")
            # Return a default list as fallback
            return ["AAPL", "MSFT", "AMZN", "GOOGL", "META"]
            
    except Exception as e:
        print(f"Error fetching S&P 500 companies: {e}")
        # Return a default list as fallback
        return ["AAPL", "MSFT", "AMZN", "GOOGL", "META"]

def main():
    """Main function to download Form 4 filings."""
    # Create an argument parser
    parser = argparse.ArgumentParser(description='Process SEC Form 4 filings.')
    parser.add_argument('--no-download', action='store_true', 
                        help='Skip downloading new filings and only process existing files')
    parser.add_argument('--limit', type=int, default=0,
                        help='Limit the number of S&P 500 companies to download (0 = all)')
    parser.add_argument('--date-range', type=str, 
                        help='Date range for downloading filings in format YYYY-MM-DD:YYYY-MM-DD')
    parser.add_argument('--debug', action='store_true', default=True,
                        help='Enable debug output')
    args = parser.parse_args()
    
    # Enable debug output for GitHub Actions
    debug = args.debug or ('GITHUB_ACTIONS' in os.environ)
    
    if debug:
        print("DEBUG: Starting InsiderTrading.py script")
        print(f"DEBUG: Current working directory: {os.getcwd()}")
        print(f"DEBUG: Data directory: {DATA_DIR}")
        print(f"DEBUG: Database path: {DB_PATH}")
        print(f"DEBUG: No-download mode: {args.no_download}")
        print(f"DEBUG: Company limit: {args.limit}")
    
    # Create data directory if it doesn't exist
    os.makedirs(DATA_DIR, exist_ok=True)
    
    if debug:
        print("DEBUG: Data directory created or verified")
        print("DEBUG: Listing files in data directory:")
        for root, dirs, files in os.walk(DATA_DIR):
            print(f"DEBUG:   Dir: {root}")
            for file in files:
                print(f"DEBUG:     File: {file}")
    
    # Initialize SQLite database
    initialize_database()
    
    if debug:
        print("DEBUG: Database initialized")
    
    if not args.no_download:
        # Only run download code if --no-download is NOT specified
        # Define date range for Form 4 filings
        if args.date_range:
            # Parse the date range from the argument (format: YYYY-MM-DD:YYYY-MM-DD)
            try:
                start_date, end_date = args.date_range.split(':')
                # Validate dates
                datetime.strptime(start_date, "%Y-%m-%d")
                datetime.strptime(end_date, "%Y-%m-%d")
                if debug:
                    print(f"DEBUG: Using custom date range: {start_date} to {end_date}")
            except ValueError as e:
                print(f"ERROR: Invalid date range format. Use YYYY-MM-DD:YYYY-MM-DD. Error: {e}")
                if debug:
                    import traceback
                    traceback.print_exc()
                return 1
        else:
            # Default to last 1 years if no date range specified
            end_date = datetime.now().strftime("%Y-%m-%d")  # Today
            start_date = (datetime.now() - timedelta(weeks=52)).strftime("%Y-%m-%d")  # 1 year ago
            if debug:
                print(f"DEBUG: Using default date range (last  year): {start_date} to {end_date}")
                
        print(f"Using sec-edgar-downloader to fetch Form 4 filings from {start_date} to {end_date}...")
        
        # Initialize the downloader with company name and user email (required by SEC)
        company_name = "S&P500 Insider Trading Research Project"
        user_email = "wescules@yahoo.com"  # Using a real email for SEC requirements
        if debug:
            print(f"DEBUG: Using company name: {company_name}")
            print(f"DEBUG: Using email: {user_email}")
        
        try:
            # The library will automatically create headers using company_name and user_email
            dl = Downloader(company_name, user_email, DATA_DIR)
            if debug:
                print("DEBUG: Downloader initialized successfully")
        except Exception as e:
            print(f"ERROR: Failed to initialize downloader: {e}")
            if debug:
                import traceback
                traceback.print_exc()
            return 1
        
        # Get S&P 500 companies dynamically
        try:
            # companies = get_sp500_companies()
            companies = get_small_cap_companies()
            if debug:
                print(f"DEBUG: Successfully fetched companies: {len(companies)}")
                print(f"DEBUG: First 5 companies: {companies[:5]}")
        except Exception as e:
            print(f"ERROR: Failed to get S&P 500 companies: {e}")
            if debug:
                import traceback
                traceback.print_exc()
            return 1
        
        # Apply limit if specified
        if args.limit > 0 and args.limit < len(companies):
            print(f"Limiting to the first {args.limit} companies (out of {len(companies)} total S&P 500 companies)")
            companies = companies[:args.limit]
            if debug:
                print(f"DEBUG: Limited to companies: {companies}")
        else:
            print(f"Processing all {len(companies)} S&P 500 companies")
        
        # Download Form 4 filings for each company
        for i, ticker in enumerate(companies):
            try:
                print(f"[{i+1}/{len(companies)}] Downloading Form 4 filings for {ticker}...")
                if debug:
                    print(f"DEBUG: Starting download for {ticker}")
                
                # Download Form 4 filings within the specified date range
                # Set download_details=True to get the XML files
                dl.get("4", ticker, after=start_date, before=end_date, download_details=True)
                print(f"Successfully downloaded Form 4 filings for {ticker}")
            except Exception as e:
                print(f"Error downloading Form 4 filings for {ticker}: {e}")
                if debug:
                    import traceback
                    traceback.print_exc()
    else:
        print("Skipping download, processing existing files only...")
        if debug:
            print("DEBUG: No-download mode, checking for existing files:")
            # List files
            for root, dirs, files in os.walk(os.path.join(DATA_DIR, "sec-edgar-filings")):
                print(f"DEBUG:   Dir: {root}")
                for file in files:
                    print(f"DEBUG:     File: {file}")
    
    # Process the downloaded Form 4 filings
    try:
        if debug:
            print("DEBUG: Starting to process Form 4 filings")
        process_form4_filings()
        if debug:
            print("DEBUG: Successfully processed Form 4 filings")
    except Exception as e:
        print(f"ERROR: Failed to process Form 4 filings: {e}")
        if debug:
            import traceback
            traceback.print_exc()
        return 1
    
    if debug:
        print("DEBUG: Script completed successfully")
    
    return 0

def initialize_database():
    """Initialize SQLite database with the required tables."""
    print("Initializing SQLite database...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create main insider trading table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS insider_trading (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        issuer_name TEXT,
        issuer_ticker TEXT,
        reporting_owner TEXT,
        reporting_owner_cik TEXT,
        reporting_owner_position TEXT,
        transaction_date TEXT,
        transaction_shares TEXT,
        transaction_price TEXT,
        transaction_type TEXT,
        shares_after_transaction TEXT,
        aff10b5One TEXT,
        source_file TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create index for faster queries
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_issuer_ticker ON insider_trading (issuer_ticker)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_transaction_date ON insider_trading (transaction_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_reporting_owner ON insider_trading (reporting_owner)')
    
    conn.commit()
    conn.close()
    
    print("Database initialized successfully")

def check_downloaded_data():
    """Examines the downloaded data structure and prints information about it."""
    print("\nChecking downloaded data structure:")
    
    # List directories and files
    if not os.path.exists(DATA_DIR):
        print(f"Error: Directory {DATA_DIR} does not exist")
        return
    
    # Count files 
    print(f"\nDirectory structure:")
    for root, dirs, files in os.walk(DATA_DIR):
        depth = root.replace(DATA_DIR, '').count(os.sep)
        indent = ' ' * 4 * depth
        print(f"{indent}{os.path.basename(root)}/")
        if depth < 2:  # Only show files for the first two levels
            for file in files:
                print(f"{indent}    {file}")
    
    # Find XML files
    xml_files = glob.glob(f"{DATA_DIR}/**/*.xml", recursive=True)
    print(f"\nFound {len(xml_files)} XML files")
    
    # Examine a sample XML file if available
    if xml_files:
        sample_file = xml_files[0]
        print(f"\nExamining sample XML file: {os.path.basename(sample_file)}")
        try:
            tree = ET.parse(sample_file)
            root = tree.getroot()
            print(f"Root tag: {root.tag}")
            print(f"Namespace: {root.attrib}")
            print("\nChild elements:")
            for child in list(root)[:5]:  # Print first 5 children
                print(f"  {child.tag}")
        except Exception as e:
            print(f"Error parsing XML: {e}")

def process_form4_filings():
    """Process the downloaded Form 4 filings to extract insider trading information."""
    print("\nProcessing Form 4 filings...")
    
    # Find all XML files (Form 4 filings are in XML format)
    xml_files = glob.glob(f"{DATA_DIR}/**/*.xml", recursive=True)
    
    if not xml_files:
        print("No XML files found to process")
        return
    
    # Connect to SQLite database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Track processed filings for summary
    processed_count = 0
    error_count = 0
    
    for xml_file in xml_files:
        try:
            # Parse the XML file
            tree = ET.parse(xml_file)
            root = tree.getroot()
            
            # Extract relevant information
            issuer_name = None
            issuer_ticker = None
            reporting_owner = None
            reporting_owner_cik = None
            reporting_owner_position = None  # New field for position
            transaction_date = None
            transaction_shares = None
            transaction_price = None
            transaction_type = None
            shares_after_transaction = None
            aff10b5One = None
            
            # Extract issuer information
            for elem in root.findall(".//issuerName"):
                issuer_name = elem.text
                break
            
            for elem in root.findall(".//issuerTradingSymbol"):
                issuer_ticker = elem.text
                break
            
            # Extract reporting owner information
            for elem in root.findall(".//rptOwnerName"):
                reporting_owner = elem.text
                break
            
            # Extract reporting owner CIK
            for elem in root.findall(".//rptOwnerCik"):
                reporting_owner_cik = elem.text
                break
            
            # Extract reporting owner position/title
            for elem in root.findall(".//reportingOwnerRelationship/officerTitle"):
                reporting_owner_position = elem.text
                break
            
            # Extract 10b5-1 plan details.
            aff10b5One = root.findtext('aff10b5One')
            
            # Extract transaction information
            # Get the first non-derivative transaction (for simplicity)
            transactions = root.findall(".//nonDerivativeTransaction") if root.findall(".//nonDerivativeTransaction") else root.findall(".//derivativeTransaction")
            if transactions:
                transaction = transactions[0]  # Get the first transaction
                
                # Extract transaction date
                date_elem = transaction.find(".//transactionDate/value")
                if date_elem is not None:
                    transaction_date = date_elem.text
                
                # Extract transaction shares
                shares_elem = transaction.find(".//transactionShares/value")
                if shares_elem is not None:
                    transaction_shares = shares_elem.text
                
                # Extract transaction price
                price_elem = transaction.find(".//transactionPricePerShare/value")
                if price_elem is not None:
                    transaction_price = price_elem.text
                
                # Extract transaction code
                code_elem = transaction.find(".//transactionCode")
                if code_elem is not None:
                    transaction_type = code_elem.text
                
                # Extract shares owned after transaction
                post_shares_elem = transaction.find(".//sharesOwnedFollowingTransaction/value")
                if post_shares_elem is not None:
                    shares_after_transaction = post_shares_elem.text
            
            # Insert into SQLite database
            cursor.execute('''
            INSERT INTO insider_trading 
            (issuer_name, issuer_ticker, reporting_owner, reporting_owner_cik, 
             reporting_owner_position, transaction_date, transaction_shares, 
             transaction_price, transaction_type, shares_after_transaction, aff10b5One, source_file)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                issuer_name, issuer_ticker, reporting_owner, reporting_owner_cik,
                reporting_owner_position, transaction_date, transaction_shares,
                transaction_price, transaction_type, shares_after_transaction, 
                aff10b5One, xml_file
            ))
            
            processed_count += 1
        
        except Exception as e:
            print(f"Error processing {xml_file}: {e}")
            error_count += 1
    
    # Commit changes and close connection
    conn.commit()
    conn.close()
    
    print(f"\nInsider Trading Data Summary:")
    print(f"Total transactions processed: {processed_count}")
    print(f"Errors encountered: {error_count}")
    
    # Display sample data from the database
    display_sample_data()

def display_sample_data():
    """Display sample data from the SQLite database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        
        # Convert SQLite data to DataFrame for easy display
        df = pd.read_sql_query("SELECT * FROM insider_trading LIMIT 5", conn)
        conn.close()
        
        if not df.empty:
            print("\nSample transactions:")
            print(df.to_string())
        else:
            print("\nNo insider trading data found in the database")
    except Exception as e:
        print(f"Error displaying sample data: {e}")

def query_insider_trading(ticker=None, date_from=None, date_to=None, limit=10):
    """Query insider trading data from the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    
    query = "SELECT * FROM insider_trading WHERE 1=1"
    params = []
    
    if ticker:
        query += " AND issuer_ticker = ?"
        params.append(ticker)
    
    if date_from:
        query += " AND transaction_date >= ?"
        params.append(date_from)
    
    if date_to:
        query += " AND transaction_date <= ?"
        params.append(date_to)
    
    query += " ORDER BY transaction_date DESC LIMIT ?"
    params.append(limit)
    
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    
    return df

if __name__ == "__main__":
    import sys
    sys.exit(main())