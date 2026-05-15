"""
Configuration constants for the BTC Trend Prediction Dashboard.
"""

# =============================================================================
# API Endpoints
# =============================================================================

BINANCE_BASE_URL = "https://api.binance.com"
BINANCE_FUTURES_URL = "https://fapi.binance.com"
SYMBOL = "BTCUSDT"

FEAR_GREED_URL = "https://api.alternative.me/fng/"

# FRED API — Free key from https://fred.stlouisfed.org/
FRED_API_KEY = "771366b57915c7813f18cfaa1dc26158 "  # Replace with your key
FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_M2_SERIES = "M2SL"

# Yahoo Finance tickers
YAHOO_DXY = "DX-Y.NYB"
YAHOO_SP500 = "^GSPC"

# Web scraping targets
FARSIDE_URL = "https://farside.co.uk/btc/"
COINGLASS_LIQ_URL = "https://www.coinglass.com/LiquidationData"

# =============================================================================
# Cache
# =============================================================================

CACHE_TTL_SECONDS = 300  # 5 minutes

# =============================================================================
# Session Times (UTC)
# =============================================================================

SESSIONS = {
    "asia": {"start": 0, "end": 8},      # 00:00 - 08:00 UTC
    "europe": {"start": 7, "end": 16},    # 07:00 - 16:00 UTC
    "new_york": {"start": 13, "end": 22}, # 13:00 - 22:00 UTC
}

# =============================================================================
# Timeframes
# =============================================================================

TIMEFRAMES = {
    "4h": {
        "kline_interval": "4h",
        "kline_limit": 200,
        "label": "4-Hour",
    },
    "1d": {
        "kline_interval": "1d",
        "kline_limit": 250,
        "label": "Daily",
    },
    "1w": {
        "kline_interval": "1w",
        "kline_limit": 52,
        "label": "Weekly",
    },
}

# =============================================================================
# Prediction Weights (per group)
# =============================================================================

GROUP_WEIGHTS = {
    "price_structure": 0.25,
    "momentum_volatility": 0.20,
    "macro_sentiment": 0.15,
    "derivatives": 0.20,
    "liquidation": 0.10,
    "session": 0.10,
}

# Timeframe weight adjustments (some indicators matter more on certain TFs)
TIMEFRAME_WEIGHT_MULTIPLIERS = {
    "4h": {
        "session": 1.5,          # Session matters more on intraday
        "macro_sentiment": 0.7,  # Macro less relevant short-term
    },
    "1d": {},  # Default weights
    "1w": {
        "session": 0.3,          # Session barely matters on weekly
        "macro_sentiment": 1.5,  # Macro matters more on weekly
        "derivatives": 0.8,
    },
}

# =============================================================================
# Server
# =============================================================================

HOST = "0.0.0.0"
PORT = 5000
DEBUG = False
