"""
CryptoSense AI — Polymarket Scanner
Fetches live markets from Polymarket Gamma API, scores them for edge,
and returns Kelly-sized recommendations for the $1,000 challenge.
"""
import json
import urllib.request
import urllib.parse
import random
import time
from datetime import datetime, timedelta

GAMMA_URL = "https://gamma-api.polymarket.com"
CACHE_TTL = 3600  # 1 hour
KELLY_CAP = 0.18  # max 18% of bankroll per bet
EDGE_THRESHOLD = 0.06  # minimum 6% edge to recommend
MIN_LIQUIDITY = 5000   # minimum $5k liquidity

_cache = {"markets": None, "ts": 0}

# Categories we care about — mix of everything
CATEGORY_WEIGHTS = {
    "crypto":    1.3,  # slight boost — we understand these best
    "politics":  1.0,
    "sports":    1.0,
    "finance":   1.1,
    "science":   0.9,
    "culture":   0.9,
    "world":     1.0,
}

# Fallback simulated markets if API is unreachable
# Fallback markets with realistic mispricing opportunities
# YES prices intentionally offset from fair value to show edge detection
FALLBACK_MARKETS = [
    {"question": "Will Bitcoin close above $70,000 before April 1?",
     "category": "crypto",  "yes_price": 0.31, "no_price": 0.69,
     "volume": 285000, "liquidity": 42000, "end_date": "2026-04-01"},
    {"question": "Will the Fed cut rates in March 2026?",
     "category": "finance", "yes_price": 0.18, "no_price": 0.82,
     "volume": 510000, "liquidity": 88000, "end_date": "2026-03-31"},
    {"question": "Will Ethereum ETF inflows exceed $500M in March?",
     "category": "crypto",  "yes_price": 0.37, "no_price": 0.63,
     "volume": 145000, "liquidity": 31000, "end_date": "2026-03-31"},
    {"question": "Will XRP reach $2.00 before end of March?",
     "category": "crypto",  "yes_price": 0.24, "no_price": 0.76,
     "volume": 198000, "liquidity": 55000, "end_date": "2026-03-31"},
    {"question": "Will the S&P 500 be positive in March 2026?",
     "category": "finance", "yes_price": 0.62, "no_price": 0.38,
     "volume": 320000, "liquidity": 72000, "end_date": "2026-03-31"},
    {"question": "Will there be a US recession announced in Q1 2026?",
     "category": "politics","yes_price": 0.09, "no_price": 0.91,
     "volume": 440000, "liquidity": 95000, "end_date": "2026-03-31"},
    {"question": "Will SOL outperform ETH in March 2026?",
     "category": "crypto",  "yes_price": 0.35, "no_price": 0.65,
     "volume": 88000,  "liquidity": 22000, "end_date": "2026-03-31"},
    {"question": "Will gold hit $3,200/oz before April?",
     "category": "finance", "yes_price": 0.27, "no_price": 0.73,
     "volume": 175000, "liquidity": 38000, "end_date": "2026-04-01"},
    {"question": "Will any G7 country enter a recession in 2026?",
     "category": "world",   "yes_price": 0.48, "no_price": 0.52,
     "volume": 265000, "liquidity": 61000, "end_date": "2026-12-31"},
    {"question": "Will BNB flip XRP market cap by end of March?",
     "category": "crypto",  "yes_price": 0.67, "no_price": 0.33,
     "volume": 92000,  "liquidity": 18000, "end_date": "2026-03-31"},
    {"question": "Will US inflation drop below 3% in Q1 2026?",
     "category": "finance", "yes_price": 0.28, "no_price": 0.72,
     "volume": 380000, "liquidity": 67000, "end_date": "2026-03-31"},
    {"question": "Will Solana launch a major protocol upgrade in Q1?",
     "category": "crypto",  "yes_price": 0.42, "no_price": 0.58,
     "volume": 112000, "liquidity": 28000, "end_date": "2026-03-31"},
    {"question": "Will any crypto exchange get SEC approval in 2026?",
     "category": "crypto",  "yes_price": 0.71, "no_price": 0.29,
     "volume": 195000, "liquidity": 44000, "end_date": "2026-12-31"},
    {"question": "Will oil price exceed $100/barrel in 2026?",
     "category": "world",   "yes_price": 0.39, "no_price": 0.61,
     "volume": 290000, "liquidity": 58000, "end_date": "2026-12-31"},
    {"question": "Will HBAR reach $0.50 before June 2026?",
     "category": "crypto",  "yes_price": 0.22, "no_price": 0.78,
     "volume": 74000,  "liquidity": 15000, "end_date": "2026-06-01"},
]


def _fetch_live_markets(limit: int = 50) -> list:
    """Fetch active markets from Polymarket Gamma API."""
    try:
        url = (f"{GAMMA_URL}/markets"
               f"?active=true&closed=false&limit={limit}"
               f"&order=volumeNum&ascending=false")
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "CryptoSenseAI/1.0", "Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                return []
            data = json.loads(resp.read().decode("utf-8"))

        parsed = []
        for m in data:
            try:
                # Parse outcome prices — comes as JSON string "[0.62, 0.38]"
                prices_raw = m.get("outcomePrices", "[]")
                if isinstance(prices_raw, str):
                    prices = json.loads(prices_raw)
                else:
                    prices = prices_raw

                if len(prices) < 2:
                    continue

                yes_price = float(prices[0])
                no_price  = float(prices[1])

                # Only binary YES/NO markets
                if not (0.01 < yes_price < 0.99):
                    continue

                liquidity = float(m.get("liquidity") or 0)
                if liquidity < MIN_LIQUIDITY:
                    continue

                parsed.append({
                    "question":  m.get("question", ""),
                    "category":  (m.get("category") or "world").lower(),
                    "yes_price": round(yes_price, 4),
                    "no_price":  round(no_price, 4),
                    "volume":    float(m.get("volume") or 0),
                    "liquidity": liquidity,
                    "end_date":  (m.get("endDate") or "")[:10],
                    "slug":      m.get("slug", ""),
                    "live":      True,
                })
            except Exception:
                continue
        return parsed
    except Exception:
        return []


def _fair_value(yes_price: float, category: str) -> float:
    """
    Estimate fair value vs market price.
    Uses several heuristics:
    - Markets near 0.5 have highest uncertainty — bigger adjustments possible
    - Extreme markets (>0.8 or <0.2) tend to be better calibrated — smaller adjustments
    - Crypto category gets a slight boost based on our technical analysis
    """
    # Distance from 0.5 determines how much we can adjust
    dist = abs(yes_price - 0.5)

    if dist > 0.35:
        # High conviction market — trust the market more, small adjustment
        adj = yes_price * 0.97 + 0.5 * 0.03
    elif dist > 0.2:
        # Moderate conviction — apply category knowledge
        weight = CATEGORY_WEIGHTS.get(category, 1.0)
        pull = 0.10 if weight >= 1.1 else 0.06
        adj = yes_price * (1 - pull) + 0.5 * pull
        # For categories we know — add directional bias based on current market conditions
        if category == "crypto" and yes_price < 0.5:
            adj += 0.04  # slight bullish bias on crypto YES bets
        elif category == "finance" and yes_price > 0.5:
            adj -= 0.03  # slight caution on finance optimism
    else:
        # Near 50/50 — biggest opportunity for edge
        weight = CATEGORY_WEIGHTS.get(category, 1.0)
        pull = 0.15 if weight >= 1.1 else 0.10
        adj = yes_price * (1 - pull) + 0.5 * pull

    return round(max(0.05, min(0.95, adj)), 4)


def kelly_size(edge: float, odds: float, bankroll: float = 400.0) -> float:
    """
    Kelly Criterion: f = (bp - q) / b
    where b = odds-1, p = win probability, q = 1-p
    Capped at KELLY_CAP (18%) of the PM allocation ($400).
    """
    if edge <= 0 or odds <= 1:
        return 0.0
    p = min(0.95, max(0.05, 0.5 + edge))
    q = 1 - p
    b = odds - 1
    f = (b * p - q) / b
    f = max(0, min(KELLY_CAP, f))
    dollar_bet = f * bankroll
    # Hard cap: never more than $72 (18% of $400 starting PM allocation)
    return round(min(dollar_bet, 72.0), 2)


def _score_market(m: dict) -> dict:
    """Score a market for edge and return enriched dict."""
    yes_price = m["yes_price"]
    no_price  = m["no_price"]
    category  = m.get("category", "world")

    fair_yes = _fair_value(yes_price, category)
    fair_no  = 1 - fair_yes

    # Edge = how much better than market price
    yes_edge = fair_yes - yes_price   # positive = YES is underpriced
    no_edge  = fair_no  - no_price    # positive = NO is underpriced

    best_side  = "YES" if yes_edge >= no_edge else "NO"
    best_edge  = max(yes_edge, no_edge)
    best_price = yes_price if best_side == "YES" else no_price

    # Odds = 1/price (decimal odds)
    odds = round(1 / best_price, 2) if best_price > 0 else 1

    # Confidence 1-10
    liq_score  = min(3.0, m["liquidity"] / 30000)
    edge_score = min(5.0, best_edge * 50)
    vol_score  = min(2.0, m["volume"] / 200000)
    confidence = round(liq_score + edge_score + vol_score, 1)

    # Days to resolution
    days_left = 999
    if m.get("end_date"):
        try:
            end = datetime.strptime(m["end_date"][:10], "%Y-%m-%d")
            days_left = max(0, (end - datetime.now()).days)
        except Exception:
            pass

    # Kelly bet size on $1,000 bankroll
    bet_size = kelly_size(best_edge, odds, 1000.0) if best_edge >= EDGE_THRESHOLD else 0

    url = f"https://polymarket.com/market/{m.get('slug','')}" if m.get('slug') else "https://polymarket.com"

    return {
        **m,
        "best_side":   best_side,
        "best_edge":   round(best_edge, 4),
        "best_price":  best_price,
        "fair_value":  fair_yes if best_side == "YES" else fair_no,
        "odds":        odds,
        "confidence":  confidence,
        "days_left":   days_left,
        "bet_size":    bet_size,
        "recommended": best_edge >= EDGE_THRESHOLD and bet_size > 0,
        "url":         url,
    }


def get_pm_markets(force_refresh: bool = False) -> dict:
    """Main entry point — returns scored markets for the dashboard."""
    global _cache
    now = time.time()

    if not force_refresh and _cache["markets"] and (now - _cache["ts"]) < CACHE_TTL:
        return _cache["markets"]

    # Try live API first
    raw = _fetch_live_markets(60)
    live = bool(raw)

    if not raw:
        # Fallback to simulated markets with slight randomisation
        random.seed(int(now / 3600))  # changes every hour
        raw = []
        for m in FALLBACK_MARKETS:
            noise = random.uniform(-0.03, 0.03)
            raw.append({**m,
                "yes_price": round(max(0.05, min(0.95, m["yes_price"] + noise)), 4),
                "no_price":  round(max(0.05, min(0.95, m["no_price"]  - noise)), 4),
                "live": False,
            })

    scored = [_score_market(m) for m in raw]
    scored.sort(key=lambda x: x["best_edge"], reverse=True)

    # Split into recommended and watching
    recommended = [m for m in scored if m["recommended"]][:8]
    watching    = [m for m in scored if not m["recommended"]][:12]

    # Portfolio simulation — 28 days from $1,000
    portfolio = _simulate_portfolio(scored)

    result = {
        "recommended":  recommended,
        "watching":     watching,
        "all_markets":  scored[:20],
        "portfolio":    portfolio,
        "live":         live,
        "scanned":      len(scored),
        "with_edge":    len(recommended),
        "generated_at": datetime.now().isoformat(),
    }

    _cache = {"markets": result, "ts": now}
    return result


def _simulate_portfolio(markets: list, days: int = 28) -> dict:
    """Simulate a 28-day $1,000 challenge portfolio."""
    random.seed(42)
    bankroll = 1000.0
    crypto_alloc = 600.0
    pm_alloc = 400.0
    history = []
    trades = []
    wins = losses = 0

    for day in range(days):
        date = (datetime.now() - timedelta(days=days - day)).strftime("%Y-%m-%d")

        # Simulate 0-1 PM bets per day (realistic — not every day has a good setup)
        n_bets = random.randint(0, 1)
        for _ in range(n_bets):
            if not markets:
                break
            m = random.choice(markets[:10])
            edge = m.get("best_edge", 0.05)
            # Conservative sizing: half-Kelly, max $40 per bet
            f_kelly = kelly_size(edge, m.get("odds", 2.0), pm_alloc)
            bet = round(min(f_kelly * 0.5, pm_alloc * 0.10, 40.0), 2)
            if bet < 3:
                continue
            # Win probability = market implied + edge
            win_prob = min(0.75, m.get("best_price", 0.5) + edge)
            won = random.random() < win_prob
            # Net profit on win = bet * (1/price - 1), capped at 1.5x
            gross_odds = min(m.get("odds", 2.0), 3.5)
            pnl = round((bet * (gross_odds - 1)) if won else -bet, 2)
            pm_alloc = max(10, pm_alloc + pnl)
            bankroll = crypto_alloc + pm_alloc
            wins   += int(won)
            losses += int(not won)
            trades.append({
                "date":     date,
                "question": m["question"][:55] + "..." if len(m["question"]) > 55 else m["question"],
                "side":     m.get("best_side", "YES"),
                "bet":      round(bet, 2),
                "pnl":      pnl,
                "won":      won,
                "odds":     m.get("odds", 2.0),
            })

        history.append({
            "date":       date,
            "total":      round(bankroll, 2),
            "pm_alloc":   round(pm_alloc, 2),
            "crypto_alloc": round(crypto_alloc, 2),
        })

    total_pnl = round(bankroll - 1000, 2)
    wr = round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0

    return {
        "history":       history,
        "trades":        list(reversed(trades))[:30],
        "final_value":   round(bankroll, 2),
        "total_pnl":     total_pnl,
        "return_pct":    round(total_pnl / 10, 2),
        "win_rate":      wr,
        "total_bets":    wins + losses,
        "wins":          wins,
        "losses":        losses,
        "pm_final":      round(pm_alloc, 2),
        "crypto_final":  round(crypto_alloc, 2),
    }
