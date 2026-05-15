"""
Pure indicator calculation functions — no I/O, no side effects.
All functions take raw data (candles, prices) and return computed values.
"""

import math
from typing import List, Optional, Tuple

from domain.models import Candle, MACDResult, PivotLevels


# =============================================================================
# GROUP 1 — Price Structure
# =============================================================================

def calc_higher_highs_lows(candles: List[Candle], lookback: int = 5) -> dict:
    """
    Analyze the last N candles for higher-high/higher-low patterns.
    Returns: {"pattern": "bullish"|"bearish"|"neutral", "hh_count": int, "hl_count": int, ...}
    """
    if len(candles) < lookback + 1:
        return {"pattern": "neutral", "hh_count": 0, "hl_count": 0, "lh_count": 0, "ll_count": 0}

    recent = candles[-(lookback + 1):]
    hh_count = 0
    hl_count = 0
    lh_count = 0
    ll_count = 0

    for i in range(1, len(recent)):
        if recent[i].high > recent[i - 1].high:
            hh_count += 1
        elif recent[i].high < recent[i - 1].high:
            lh_count += 1

        if recent[i].low > recent[i - 1].low:
            hl_count += 1
        elif recent[i].low < recent[i - 1].low:
            ll_count += 1

    if hh_count >= 3 and hl_count >= 3:
        pattern = "bullish"
    elif lh_count >= 3 and ll_count >= 3:
        pattern = "bearish"
    else:
        pattern = "neutral"

    return {
        "pattern": pattern,
        "hh_count": hh_count,
        "hl_count": hl_count,
        "lh_count": lh_count,
        "ll_count": ll_count,
    }


def calc_sma(closes: List[float], period: int) -> Optional[float]:
    """Simple Moving Average."""
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def calc_ema(closes: List[float], period: int) -> List[float]:
    """Exponential Moving Average — returns full EMA series."""
    if len(closes) < period:
        return []

    multiplier = 2 / (period + 1)
    ema = [sum(closes[:period]) / period]

    for price in closes[period:]:
        ema.append((price - ema[-1]) * multiplier + ema[-1])

    return ema


def calc_price_vs_ma(closes: List[float], period: int) -> dict:
    """
    Compare current price to MA.
    Returns: {"ma": float, "price": float, "distance_pct": float, "above": bool}
    """
    ma = calc_sma(closes, period)
    if ma is None or ma == 0:
        return {"ma": None, "price": closes[-1], "distance_pct": 0, "above": True}

    price = closes[-1]
    distance_pct = ((price - ma) / ma) * 100

    return {
        "ma": round(ma, 2),
        "price": round(price, 2),
        "distance_pct": round(distance_pct, 2),
        "above": price > ma,
    }


def calc_pivot_levels(candles: List[Candle]) -> Optional[PivotLevels]:
    """
    Classic pivot points from the previous period's candle.
    Uses the last completed candle.
    """
    if len(candles) < 2:
        return None

    prev = candles[-2]
    h, l, c = prev.high, prev.low, prev.close

    pp = (h + l + c) / 3
    r1 = 2 * pp - l
    s1 = 2 * pp - h
    r2 = pp + (h - l)
    s2 = pp - (h - l)
    r3 = h + 2 * (pp - l)
    s3 = l - 2 * (h - pp)

    return PivotLevels(
        pp=round(pp, 2),
        r1=round(r1, 2), r2=round(r2, 2), r3=round(r3, 2),
        s1=round(s1, 2), s2=round(s2, 2), s3=round(s3, 2),
    )


def calc_session_high_low(hourly_candles: List[Candle], session_start: int, session_end: int) -> dict:
    """
    Calculate the high and low of a specific trading session.
    session_start / session_end are UTC hours.
    """
    from datetime import datetime, timezone

    session_candles = []
    for c in hourly_candles:
        dt = datetime.fromtimestamp(c.timestamp / 1000, tz=timezone.utc)
        hour = dt.hour
        if session_start <= hour < session_end:
            session_candles.append(c)

    if not session_candles:
        return {"high": None, "low": None, "available": False}

    high = max(c.high for c in session_candles)
    low = min(c.low for c in session_candles)

    return {"high": round(high, 2), "low": round(low, 2), "available": True}


def calc_cme_gap(daily_candles: List[Candle]) -> dict:
    """
    Detect CME gap: difference between Friday close and Monday open.
    Uses timestamps to detect weekend gaps.
    """
    from datetime import datetime, timezone

    if len(daily_candles) < 2:
        return {"gap": 0, "gap_pct": 0, "direction": "none", "filled": True}

    for i in range(len(daily_candles) - 1, 0, -1):
        curr = daily_candles[i]
        prev = daily_candles[i - 1]

        curr_dt = datetime.fromtimestamp(curr.timestamp / 1000, tz=timezone.utc)
        prev_dt = datetime.fromtimestamp(prev.timestamp / 1000, tz=timezone.utc)

        # Detect weekend gap (more than 1 day between candles, or Monday)
        day_diff = (curr_dt - prev_dt).days
        if day_diff >= 2 or curr_dt.weekday() == 0:  # Monday
            gap = curr.open - prev.close
            gap_pct = (gap / prev.close) * 100 if prev.close else 0

            # Check if gap has been filled
            if gap > 0:
                filled = curr.low <= prev.close
                direction = "up"
            elif gap < 0:
                filled = curr.high >= prev.close
                direction = "down"
            else:
                filled = True
                direction = "none"

            return {
                "gap": round(gap, 2),
                "gap_pct": round(gap_pct, 2),
                "direction": direction,
                "filled": filled,
                "friday_close": round(prev.close, 2),
                "monday_open": round(curr.open, 2),
            }

    return {"gap": 0, "gap_pct": 0, "direction": "none", "filled": True}


# =============================================================================
# GROUP 2 — Momentum & Volatility
# =============================================================================

def calc_rsi(closes: List[float], period: int = 14) -> Optional[float]:
    """Relative Strength Index."""
    if len(closes) < period + 1:
        return None

    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]

    gains = [d if d > 0 else 0 for d in deltas[:period]]
    losses = [-d if d < 0 else 0 for d in deltas[:period]]

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    for d in deltas[period:]:
        gain = d if d > 0 else 0
        loss = -d if d < 0 else 0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 2)


def calc_macd(closes: List[float],
              fast: int = 12, slow: int = 26, signal_period: int = 9) -> Optional[MACDResult]:
    """MACD (Moving Average Convergence Divergence)."""
    if len(closes) < slow + signal_period:
        return None

    ema_fast = calc_ema(closes, fast)
    ema_slow = calc_ema(closes, slow)

    # Align lengths
    offset = slow - fast
    ema_fast_aligned = ema_fast[offset:]

    if len(ema_fast_aligned) != len(ema_slow):
        min_len = min(len(ema_fast_aligned), len(ema_slow))
        ema_fast_aligned = ema_fast_aligned[-min_len:]
        ema_slow = ema_slow[-min_len:]

    macd_line_series = [f - s for f, s in zip(ema_fast_aligned, ema_slow)]

    if len(macd_line_series) < signal_period:
        return None

    signal_series = calc_ema(macd_line_series, signal_period)

    if not signal_series:
        return None

    macd_val = macd_line_series[-1]
    signal_val = signal_series[-1]
    histogram = macd_val - signal_val

    return MACDResult(
        macd_line=round(macd_val, 2),
        signal_line=round(signal_val, 2),
        histogram=round(histogram, 2),
    )


def calc_volume_vs_avg(candles: List[Candle], period: int = 20) -> dict:
    """Compare current volume to N-period average."""
    if len(candles) < period + 1:
        return {"ratio": 1.0, "current": 0, "average": 0}

    volumes = [c.volume for c in candles]
    avg_vol = sum(volumes[-(period + 1):-1]) / period
    current_vol = volumes[-1]

    ratio = current_vol / avg_vol if avg_vol > 0 else 1.0

    return {
        "ratio": round(ratio, 2),
        "current": round(current_vol, 2),
        "average": round(avg_vol, 2),
    }


def calc_volume_up_down(candles: List[Candle], period: int = 20) -> dict:
    """Classify volume on up vs down candles."""
    recent = candles[-period:]

    up_vol = sum(c.volume for c in recent if c.close >= c.open)
    down_vol = sum(c.volume for c in recent if c.close < c.open)
    total = up_vol + down_vol

    if total == 0:
        return {"up_pct": 50, "down_pct": 50, "ratio": 1.0}

    up_pct = (up_vol / total) * 100
    down_pct = (down_vol / total) * 100

    return {
        "up_pct": round(up_pct, 1),
        "down_pct": round(down_pct, 1),
        "ratio": round(up_vol / down_vol, 2) if down_vol > 0 else 999,
    }


def calc_atr(candles: List[Candle], period: int = 14) -> dict:
    """Average True Range and ATR as % of price."""
    if len(candles) < period + 1:
        return {"atr": 0, "atr_pct": 0}

    true_ranges = []
    for i in range(1, len(candles)):
        c = candles[i]
        prev_close = candles[i - 1].close
        tr = max(c.high - c.low, abs(c.high - prev_close), abs(c.low - prev_close))
        true_ranges.append(tr)

    atr = sum(true_ranges[-period:]) / period
    price = candles[-1].close
    atr_pct = (atr / price) * 100 if price > 0 else 0

    return {
        "atr": round(atr, 2),
        "atr_pct": round(atr_pct, 2),
    }


def calc_bollinger_width(closes: List[float], period: int = 20, std_dev: float = 2.0) -> dict:
    """Bollinger Band Width = (Upper - Lower) / Middle."""
    if len(closes) < period:
        return {"width": 0, "upper": 0, "lower": 0, "middle": 0}

    window = closes[-period:]
    middle = sum(window) / period
    variance = sum((x - middle) ** 2 for x in window) / period
    std = math.sqrt(variance)

    upper = middle + std_dev * std
    lower = middle - std_dev * std
    width = ((upper - lower) / middle) * 100 if middle > 0 else 0

    return {
        "width": round(width, 2),
        "upper": round(upper, 2),
        "lower": round(lower, 2),
        "middle": round(middle, 2),
    }


def calc_historical_volatility(closes: List[float], period: int = 20) -> Optional[float]:
    """
    Historical Volatility (HV20) — annualized standard deviation of log returns.
    Returns percentage value.
    """
    if len(closes) < period + 1:
        return None

    log_returns = [math.log(closes[i] / closes[i - 1])
                   for i in range(len(closes) - period, len(closes))
                   if closes[i - 1] > 0]

    if len(log_returns) < period:
        return None

    mean = sum(log_returns) / len(log_returns)
    variance = sum((r - mean) ** 2 for r in log_returns) / (len(log_returns) - 1)
    std = math.sqrt(variance)

    # Annualize: multiply by sqrt(365) for crypto (24/7 market)
    hv = std * math.sqrt(365) * 100

    return round(hv, 2)


# =============================================================================
# GROUP 3 — Macro / Sentiment (scoring helpers)
# =============================================================================

def calc_trend_direction(closes: List[float], lookback: int = 5) -> dict:
    """Simple trend detection: is the series rising or falling over N periods?"""
    if len(closes) < lookback:
        return {"direction": "neutral", "change_pct": 0}

    recent = closes[-lookback:]
    change = recent[-1] - recent[0]
    change_pct = (change / recent[0]) * 100 if recent[0] != 0 else 0

    if change_pct > 0.5:
        direction = "rising"
    elif change_pct < -0.5:
        direction = "falling"
    else:
        direction = "flat"

    return {"direction": direction, "change_pct": round(change_pct, 2)}


# =============================================================================
# GROUP 4 — Derivatives
# =============================================================================

def calc_cvd_approximation(candles: List[Candle], period: int = 20) -> dict:
    """
    Approximate Cumulative Volume Delta from kline data.
    Uses taker_buy_volume: CVD = sum(taker_buy_vol - (total_vol - taker_buy_vol))
    """
    recent = candles[-period:]

    cumulative = 0
    deltas = []
    for c in recent:
        buy_vol = c.taker_buy_volume
        sell_vol = c.volume - buy_vol
        delta = buy_vol - sell_vol
        cumulative += delta
        deltas.append(delta)

    recent_trend = sum(deltas[-5:]) if len(deltas) >= 5 else sum(deltas)

    return {
        "cvd": round(cumulative, 2),
        "trend": "positive" if recent_trend > 0 else "negative" if recent_trend < 0 else "flat",
        "recent_delta": round(recent_trend, 2),
    }


# =============================================================================
# SESSION WEIGHTING
# =============================================================================

def get_current_session(utc_hour: int) -> Tuple[str, str, float]:
    """
    Determine the current trading session and its volume weight.
    Returns: (session_name, label, weight_multiplier)
    """
    if 13 <= utc_hour < 16:
        return ("overlap_eu_ny", "EU/NY Overlap", 1.3)
    elif 13 <= utc_hour < 22:
        return ("new_york", "New York", 1.2)
    elif 7 <= utc_hour < 16:
        return ("europe", "London/Europe", 1.0)
    elif 0 <= utc_hour < 8:
        return ("asia", "Asia/Pacific", 0.7)
    else:
        return ("off_hours", "Off-Hours", 0.5)
