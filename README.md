# insider-trading-analyzer
A Python project that downloads Form 4 and Form 144 SEC filings, filters for high-signal insider trades, cross-references market signals, and supports backtesting.


# Insider Screener & Alerts Bot

A Python project that downloads Form 4 and Form 144 SEC filings, filters for high-signal insider trades, cross-references market signals, and supports backtesting.

## Features
- Parses and stores insider filings into DuckDB
- Screens for high-value and cluster insider buys
- Cross-references earnings, news, and short interest
- Backtests historical success of trades

## Getting Started
```bash
pip install -r requirements.txt
python download_filings.py
python scripts/filters.py --min_buy 100000
python scripts/backtest.py --days 30
```

---



Here’s a **project roadmap** for building a professional-grade **Screener + Alerts Bot** for Form 4 and Form 144 filings, with filters, signal enrichment, and backtesting. This is broken into **4 milestone phases**:

---

## 🔹 **Phase 1: Data Pipeline & Storage**

### ✅ Goal: Extract and store Form 4 & 144 filings into DuckDB

#### Tasks:

* [ ] Write a **Python script or scheduled job** to download daily filings from the SEC EDGAR FTP/API

  * Use [`sec-edgar-downloader`](https://github.com/jadchaar/sec-edgar-downloader) or scrape raw XML
* [ ] Parse **Form 4**:

  * `insider name`, `ticker`, `transaction date`, `filing date`, `shares`, `price`, `ownership type`, `10b5-1 flag`, etc.
* [ ] Parse **Form 144**:

  * `intended sale date`, `shares`, `value`, `filing date`, etc.
* [ ] Normalize and clean the data
* [ ] Save all records into **DuckDB**:

  * Use schema similar to what we discussed earlier
  * Use Parquet as long-term archival format

#### Deliverables:

* `download_filings.py`
* DuckDB database file `insider_data.duckdb`


---

## 🔹 **Phase 2: Filtering Engine**

### ✅ Goal: Add filters to detect high-signal events

#### Filters to implement:

* [ ] **Officer Buys > \$100K**
* [ ] **Cluster Buys**: 2+ insiders buying within ±3 days
* [ ] **Exclude 10b5-1 plan** trades
* [ ] **CEO/CFO-specific buys**
* [ ] **Non-option transactions only**
* [ ] **Form 144 signal filter**: Scheduled sales + large size
* [ ] Add custom flags: `is_cluster_buy`, `is_high_value_buy`, etc.

#### Deliverables:

* `filters.py`: functions to run queries against DuckDB
* Configurable CLI:

  ```bash
  python screen.py --min_buy 100000 --cluster_window 3
  ```

---

## 🔹 **Phase 3: Signal Enrichment & Alerts**

### ✅ Goal: Cross-reference with other market data sources

#### Data Sources to Integrate:

* [ ] **Earnings calendar** (e.g., EODHD, Yahoo Finance, or Nasdaq API)
* [ ] **Analyst upgrades/downgrades** (Finviz scrape, MarketBeat, Barchart)
* [ ] **Short interest** (e.g., via FINRA or third-party APIs)
* [ ] **News headlines** (e.g., RSS feeds, Benzinga, or scraping Yahoo News)
* [ ] Flag if insider trade occurred **before earnings, after downgrade, or on high short interest**

#### Deliverables:

* `enrich_signals.py`: joins filing data with enrichment signals
* `alerts.py`: outputs summary alerts to email/Slack/Telegram

---

## 🔹 **Phase 4: Backtesting Engine**

### ✅ Goal: Test predictive power of insider trades

#### Tasks:

* [ ] Load **historical price data** (Alpha Vantage, Polygon, Yahoo Finance, etc.)
* [ ] Join filing date with price history:

  * Compute **% return after 7, 14, 30, 60 days**
  * Label trades as “successful” if return > threshold
* [ ] Support backtest filters:

  ```bash
  python backtest.py --filter "officer_buys > 100000 AND cluster = True"
  ```

#### Deliverables:

* `backtest.py`: returns distribution of returns per filter
* Summary report: hit rate, average return, drawdown

---

## 🔧 Tools & Stack

| Tool                                     | Purpose                          |
| ---------------------------------------- | -------------------------------- |
| `DuckDB`                                 | Local fast querying & analytics  |
| `Python`                                 | Core logic, scraping, processing |
| `pandas`                                 | Data wrangling                   |
| `sec-edgar-downloader` or raw `requests` | EDGAR download                   |
| `plotly` or `matplotlib`                 | For charting backtest results    |
| `rich` or `typer`                        | CLI interface                    |
| `cron` / `APScheduler`                   | Scheduling downloads             |
| `Slack` / `Telegram` bot                 | Alerts (optional)                |

---

## 🏁 Optional Future Add-ons

* UI dashboard (e.g., Streamlit or Dash)
* Insider heatmap by sector
* Sentiment overlay from social media/news
* Broker API alerts (e.g., Alpaca or IBKR paper trading)

---
