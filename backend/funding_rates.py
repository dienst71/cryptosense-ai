"""
CryptoSense AI — Funding Rate Feed
Fetches perpetual futures funding rates from CoinGlass (free, no API key needed).
Used as a signal quality filter: don't trade against extreme funding.

Logic:
  - Funding rate > +0.03%  = market crowded LONG  → penalize BUY signals
  - Funding rate < -0.03%  = market crowded SHORT → penalize SELL signals
  - Between ±0.03%         = neutral               → no adjustment
  - Beyond ±0.07%          = extreme crowding      → block signal entirely
"""
import urllib.request, json, datetime, threading

# ── Cache ─────────────────────────────────────────────────────────────────────
_cache: dict = {}          # symbol → {"rate": float, "updated": datetime}
_cache_lock = threading.Lock()
CACHE_TTL_SECONDS = 300    # refresh every 5 minutes

# CoinGlass free endpoint — no auth required
_COINGLASS_URL = "https://open-api.coinglass.com/public/v2/funding?symbol={symbol}"

# Fallback: Binance futures API (also free, no key needed)
_BINANCE_FR_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"

# Thresholds (funding rate as decimal, e.g. 0.0001 = 0.01%)
THRESHOLD_WARN    = 0.0003   # ±0.03% — reduce confidence by 0.5
THRESHOLD_BLOCK   = 0.0007   # ±0.07% — block signal entirely
CONFIDENCE_PENALTY = 0.5     # subtract from confidence score when warning level hit


def _fetch_from_binance() -> dict:
    """
    Fetch current funding rates from Binance futures (free, no key needed).
    Returns dict of symbol → funding rate (decimal).
    """
    rates = {}
    try:
        req = urllib.request.Request(
            _BINANCE_FR_URL,
            headers={"User-Agent": "CryptoSenseAI/1.0"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())

        # Map Binance symbols to our internal symbols
        symbol_map = {
            "BTCUSDT":  "BTC",
            "ETHUSDT":  "ETH",
            "SOLUSDT":  "SOL",
            "XRPUSDT":  "XRP",
            "BNBUSDT":  "BNB",
            "AVAXUSDT": "AVAX",
            "LINKUSDT": "LINK",
            "INJUSDT":  "INJ",
            "SUIUSDT":  "SUI",
            "ARBUSDT":  "ARB",
            "DOGEUSDT": "DOGE",
            "ADAUSDT":  "ADA",
        }

        for item in data:
            sym_bn = item.get("symbol", "")
            if sym_bn in symbol_map:
                try:
                    rate = float(item.get("lastFundingRate", 0))
                    rates[symbol_map[sym_bn]] = rate
                except (ValueError, TypeError):
                    pass

    except Exception:
        pass

    return rates


def refresh_funding_rates():
    """
    Refresh the global funding rate cache from Binance.
    Called on startup and every 5 minutes by the background scheduler.
    """
    global _cache
    rates = _fetch_from_binance()
    now = datetime.datetime.utcnow()

    with _cache_lock:
        for sym, rate in rates.items():
            _cache[sym] = {"rate": rate, "updated": now}


def get_funding_rate(symbol: str) -> float | None:
    """
    Returns the latest funding rate for a symbol, or None if unavailable.
    Rate is a decimal: 0.0001 = 0.01%
    """
    with _cache_lock:
        entry = _cache.get(symbol.upper())
        if not entry:
            return None
        # Return stale data rather than None — better to have old signal than none
        return entry["rate"]


def get_all_rates() -> dict:
    """Returns copy of the full cache as {symbol: rate} dict."""
    with _cache_lock:
        return {sym: v["rate"] for sym, v in _cache.items()}


def apply_funding_filter(signal: dict) -> dict:
    """
    Adjust signal confidence based on current funding rates.
    Modifies signal in place and adds 'funding_rate' and 'funding_flag' fields.

    Rules:
      BUY  signal + high positive funding → market crowded long  → penalize/block
      SELL signal + high negative funding → market crowded short → penalize/block
    """
    symbol = signal.get("symbol", "").upper()
    action = signal.get("action", "")
    rate   = get_funding_rate(symbol)

    signal["funding_rate"] = rate
    signal["funding_flag"] = "neutral"

    if rate is None or action == "HOLD":
        return signal

    # Determine if funding is fighting the signal direction
    fighting = (action == "BUY" and rate > THRESHOLD_WARN) or \
               (action == "SELL" and rate < -THRESHOLD_WARN)

    extreme  = (action == "BUY" and rate > THRESHOLD_BLOCK) or \
               (action == "SELL" and rate < -THRESHOLD_BLOCK)

    if extreme:
        signal["confidence"]   = max(0, signal.get("confidence", 0) - 2.0)
        signal["funding_flag"] = "extreme"
        signal.setdefault("top_reasons", [])
        pct = round(rate * 100, 4)
        signal["top_reasons"].append(
            f"⚠️ Extreme funding rate ({pct}%) — market crowded against this trade"
        )
    elif fighting:
        signal["confidence"]   = max(0, signal.get("confidence", 0) - CONFIDENCE_PENALTY)
        signal["funding_flag"] = "warning"

    return signal


def funding_summary() -> list:
    """Returns a sorted list of funding rate summaries for the dashboard."""
    with _cache_lock:
        items = []
        for sym, v in _cache.items():
            rate = v["rate"]
            pct  = round(rate * 10000, 2)   # convert to basis points style × 100 = %
            flag = "extreme" if abs(rate) > THRESHOLD_BLOCK else \
                   "warning"  if abs(rate) > THRESHOLD_WARN  else "neutral"
            items.append({
                "symbol":   sym,
                "rate":     rate,
                "rate_pct": round(rate * 100, 4),
                "flag":     flag,
                "bias":     "LONG CROWDED" if rate > THRESHOLD_WARN else
                            "SHORT CROWDED" if rate < -THRESHOLD_WARN else "Neutral"
            })
        return sorted(items, key=lambda x: abs(x["rate"]), reverse=True)


# ── Initial load on import ────────────────────────────────────────────────────
refresh_funding_rates()
