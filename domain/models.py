"""
Domain models — pure data classes with no external dependencies.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Candle:
    """Single OHLCV candle."""
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    taker_buy_volume: float = 0.0


@dataclass
class IndicatorResult:
    """Result of a single indicator calculation."""
    id: int
    name: str
    group: str
    value: Optional[float]          # Raw value (e.g., RSI=65.2)
    score: float                    # Normalized score: -1.0 to +1.0
    signal: str                     # "bullish" | "bearish" | "neutral"
    label: str                      # Human-readable label (e.g., "RSI: 65.2 — Bullish Momentum")
    detail: Optional[str] = None    # Extra context
    available: bool = True          # Whether data was available


@dataclass
class PivotLevels:
    """Classic pivot point support/resistance levels."""
    pp: float    # Pivot Point
    r1: float    # Resistance 1
    r2: float    # Resistance 2
    r3: float    # Resistance 3
    s1: float    # Support 1
    s2: float    # Support 2
    s3: float    # Support 3


@dataclass
class MACDResult:
    """MACD calculation result."""
    macd_line: float
    signal_line: float
    histogram: float


@dataclass
class SessionInfo:
    """Current trading session information."""
    name: str           # "asia" | "europe" | "new_york" | "overlap"
    label: str          # "Asia Session"
    weight: float       # Volume weight multiplier
    is_active: bool


@dataclass
class PredictionResult:
    """Final prediction output for a timeframe."""
    timeframe: str                              # "4h" | "1d" | "1w"
    timeframe_label: str                        # "4-Hour" | "Daily" | "Weekly"
    composite_score: float                      # -1.0 to +1.0
    direction: str                              # "bullish" | "bearish" | "neutral"
    confidence: float                           # 0-100%
    estimated_move_pct: float                   # Estimated % move
    estimated_range_low: float                  # Price range low
    estimated_range_high: float                 # Price range high
    current_price: float
    indicators: list = field(default_factory=list)   # List[IndicatorResult]
    groups: dict = field(default_factory=dict)        # Group scores


@dataclass
class DashboardData:
    """Complete dashboard response."""
    current_price: float
    price_change_24h: float
    price_change_pct_24h: float
    predictions: list = field(default_factory=list)   # List[PredictionResult]
    session: Optional[SessionInfo] = None
    last_updated: str = ""
    errors: list = field(default_factory=list)
