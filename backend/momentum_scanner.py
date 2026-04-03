
import urllib.request, json, time, datetime

COINGECKO_TOP_GAINERS = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=percent_change_24h&per_page=50&page=1&price_change_percentage=1h,24h"
COINGECKO_TRENDING    = "https://api.coingecko.com/api/v3/search/trending"

MIN_1H_MOVE    = 15.0
MIN_24H_MOVE   = 25.0
MAX_MARKET_CAP = 500_000_000
MIN_VOLUME     = 1_000_000
ALERT_COOLDOWN = 3600 * 4

_alerted = set()
_alerted_ttl = {}

def _fetch(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CryptoSenseAI/1.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None

def _clean_alerted():
    now = time.time()
    expired = [k for k, ts in _alerted_ttl.items() if now - ts > ALERT_COOLDOWN]
    for k in expired:
        _alerted.discard(k)
        del _alerted_ttl[k]

def scan_momentum():
    _clean_alerted()
    alerts = []
    trending_data = _fetch(COINGECKO_TRENDING)
    trending_ids = set()
    if trending_data:
        for item in trending_data.get("coins", []):
            trending_ids.add(item.get("item", {}).get("id", ""))
    coins = _fetch(COINGECKO_TOP_GAINERS) or []
    for c in coins:
        try:
            ticker     = c.get("symbol", "").upper()
            name       = c.get("name", ticker)
            coin_id    = c.get("id", "")
            price      = float(c.get("current_price") or 0)
            market_cap = float(c.get("market_cap") or 0)
            volume     = float(c.get("total_volume") or 0)
            move_1h    = float(c.get("price_change_percentage_1h_in_currency") or 0)
            move_24h   = float(c.get("price_change_percentage_24h") or 0)
            if ticker in _alerted: continue
            if market_cap > MAX_MARKET_CAP and market_cap != 0: continue
            if volume < MIN_VOLUME: continue
            if move_1h < MIN_1H_MOVE and move_24h < MIN_24H_MOVE: continue
            is_trending = coin_id in trending_ids
            score = 0
            if move_1h >= 30:    score += 3
            elif move_1h >= 20:  score += 2
            elif move_1h >= 15:  score += 1
            if move_24h >= 50:   score += 3
            elif move_24h >= 30: score += 2
            elif move_24h >= 25: score += 1
            if is_trending:      score += 2
            if volume > 10_000_000: score += 1
            if score < 2: continue
            alerts.append({
                "ticker": ticker, "name": name, "coin_id": coin_id,
                "price": price, "market_cap": market_cap, "volume_24h": volume,
                "move_1h": round(move_1h, 2), "move_24h": round(move_24h, 2),
                "is_trending": is_trending, "score": score,
                "url": f"https://www.coingecko.com/en/coins/{coin_id}",
                "suggested_size": "$50-100",
                "risk": "HIGH - momentum trade, quick in/out only",
                "scanned_at": datetime.datetime.now().isoformat(),
            })
            _alerted.add(ticker)
            _alerted_ttl[ticker] = time.time()
        except Exception:
            continue
    alerts.sort(key=lambda x: x["score"], reverse=True)
    return alerts[:5]

def format_momentum_alert(coin):
    trend_tag = " TRENDING" if coin["is_trending"] else ""
    mc  = f"${coin['market_cap']/1e6:.1f}M" if coin["market_cap"] else "unknown"
    vol = f"${coin['volume_24h']/1e6:.1f}M"
    return (
        f"MOMENTUM ALERT{trend_tag}\n"
        f"---\n"
        f"*{coin['name']}* (${coin['ticker']})\n"
        f"Price: ${coin['price']:.6g}\n"
        f"1h: *+{coin['move_1h']}%* / 24h: *+{coin['move_24h']}%*\n"
        f"Volume: {vol} / MCap: {mc}\n"
        f"Risk: {coin['risk']}\n"
        f"Size: {coin['suggested_size']}\n"
        f"CoinGecko: {coin['url']}\n"
        f"Momentum alert only - verify before entering"
    )
