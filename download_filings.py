import glob
import os
import re
import io
import argparse  # for --no download option command line argument
from datetime import datetime, timedelta
from urllib.parse import urlparse
import asyncio
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
import sqlite3

from sec_downloader import Downloader
from sec_downloader.types import RequestedFilings
import aiohttp
from tqdm import tqdm
import pandas as pd
import requests

dl = Downloader("MyCompanyName", "email@example.com")

semaphore = asyncio.Semaphore(5)  # SEC limits to 10 requests/sec but this should slow it down to not hit rate limit

# Use relative path for data directory
FORM4_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'form4data')
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
DB_PATH = os.path.join(DATA_DIR, 'insider_trading.db')
URL_PATH = os.path.join(DATA_DIR, 'url.txt')
SMALL_CAP_COMPANIES = os.path.join(DATA_DIR, "small_cap_companies.csv")

SP500_URL = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"

MAX_FILING_DAYS = 365  # Only get filings < 1 year ago by default
MAX_FILING_LIMIT = 5000
ALL_FILENAMES = set()

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

HEADERS = {
    "User-Agent": "MyCompanyName (email@example.com)",
    "Accept-Encoding": "gzip, deflate",
    "Host": "www.sec.gov"
}

def is_valid_url(url):
    parsed = urlparse(url)
    return all([parsed.scheme, parsed.netloc])

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name)

# Extract company name from XML
def get_company_name_from_xml(content):
    try:
        root = ET.fromstring(content)
        issuer = root.find(".//issuer")
        if issuer is not None:
            name_tag = issuer.find("issuerTradingSymbol")
            if name_tag is not None:
                return sanitize_filename(name_tag.text)
    except Exception:
        pass
    return "Unknown"

async def download_and_save_xml(session, url):
    filename = url.replace("https://www.sec.gov/Archives/edgar/data/", "")
    filename = filename.replace('/', '-')
    if filename in ALL_FILENAMES:
        print("Skipping download. Already have a local copy")
        return
    async with semaphore:  # Enforce max 10 concurrent requests
        async with session.get(url, headers=HEADERS) as resp:
            if resp.status == 200:
                content = await resp.read()
                company_name = get_company_name_from_xml(content)
                output_dir = os.path.join(FORM4_DATA_DIR, company_name)
                os.makedirs(output_dir, exist_ok=True)
                output_path = os.path.join(output_dir, filename)
                
                with open(output_path, "wb") as f:
                    f.write(content)
            else:
                print(resp)

async def save_xmls_to_file(xml_urls):
    async with aiohttp.ClientSession() as session:
        tasks = [download_and_save_xml(session, url) for url in xml_urls]
        for t in tqdm(asyncio.as_completed(tasks), total=len(tasks)):
            await t

def process_form4_filings():
    """Process the downloaded Form 4 filings to extract insider trading information."""
    print("\nProcessing Form 4 filings...")
    
    # Find all XML files (Form 4 filings are in XML format)
    xml_files = glob.glob(f"{FORM4_DATA_DIR}/**/*.xml", recursive=True)
    
    if not xml_files:
        print("No XML files found to process")
        return
    
    # Connect to SQLite database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Track processed filings for summary
    processed_count = 0
    error_count = 0
    
    for xml_file in tqdm(xml_files):
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




def read_urls_from_file():
    with open(URL_PATH, 'r') as file:
        urls = [line.strip() for line in file if line.strip() and is_valid_url(line.strip())]
        filenames = [url.replace("https://www.sec.gov/Archives/edgar/data/", "").replace('/', '-') for url in urls]
        ALL_FILENAMES = set(filenames)
        return urls

def fetch_company_urls(company):
    try:
        print(f"Getting metadata for: {company}")
        metadatas = dl.get_filing_metadatas(
            RequestedFilings(ticker_or_cik=company, form_type="4", limit=MAX_FILING_LIMIT)
        )
        urls = []
        for metadata in metadatas:
            report_date = datetime.strptime(metadata.report_date, "%Y-%m-%d").date()
            one_year_ago = datetime.today().date() - timedelta(days=MAX_FILING_DAYS)
            is_recent = report_date > one_year_ago
            if is_recent:
                urls.append(metadata.primary_doc_url)
        print(f"Adding {len(urls)} xmls to list for company: {company}")
        
        with open(URL_PATH, "a") as f:
            for url in urls:
                f.write(url + '\n')
    except Exception as e:
        print(f"Error with {company}: {e}")
        return []

def write_urls_to_file(urls):
    with open(URL_PATH, "a") as f:
        for url in urls:
            f.write(url + '\n')

async def process_company(executor, company):
    async with semaphore:  # Enforce max 10 concurrent requests
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(executor, fetch_company_urls, company)

async def fetch_and_write_xml_urls_to_file():
    companies = get_small_cap_companies()
    open(URL_PATH, "w").close() # Clear the file

    with ThreadPoolExecutor(max_workers=10) as executor:
        tasks = [process_company(executor, company) for company in companies]
        await asyncio.gather(*tasks)

# Entry point
if __name__ == "__main__":
    """Main function to download Form 4 filings."""
    # Create an argument parser
    parser = argparse.ArgumentParser(description='Process SEC Form 4 filings.')
    parser.add_argument('--skip-download', action='store_true', 
                        help='Skip downloading new filings and only process existing files')
    parser.add_argument('--skip-fetch-urls', action='store_true', 
                        help='Skip fetching URLs and ')
    parser.add_argument('--date-range', type=str, 
                        help='Day range for downloading filings in. Enter number of days. Ex: 365')
    parser.add_argument('--limit', type=int, default=0,
                        help='Limit the number of S&P 500 companies to download (0 = all)')
    parser.add_argument('--debug', action='store_true', default=True,
                        help='Enable debug output')
    args = parser.parse_args()

    if args.date_range:
        MAX_FILING_DAYS = args.date_range
    if args.limit:
        MAX_FILING_LIMIT = args.limit
    if not args.skip_download:
        if not args.skip_fetch_urls:
            asyncio.run(fetch_and_write_xml_urls_to_file())
            print("Finished fetching and writing urls, proceeding to read from file...")
        
        xml_urls = read_urls_from_file()
        print("Finished reading file, proceeding to fetch xmls...")
        asyncio.run(save_xmls_to_file(xml_urls))

    # Initialize SQLite database
    initialize_database()
    
    # Process the downloaded Form 4 filings
    try:
        if args.debug:
            print("DEBUG: Starting to process Form 4 filings")
        process_form4_filings()
        if args.debug:
            print("DEBUG: Successfully processed Form 4 filings")
    except Exception as e:
        print(f"ERROR: Failed to process Form 4 filings: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()

    
