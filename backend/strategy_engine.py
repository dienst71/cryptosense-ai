"""CryptoSense AI — 4-Strategy Competition Engine with Rich Trade History"""
import numpy as np
import random
from datetime import datetime, timedelta

random.seed(99)
np.random.seed(99)

STRATEGIES = [
    {"id":1,"name":"Momentum","color":"#00d4ff","style":"Trend Following",
     "description":"Rides established trends. Buys when price momentum is strong, sells when momentum fades. Works best in sustained bull runs.",
     "allocations":{"XRP":0.15,"XLM":0.15,"HBAR":0.15,"BTC":0.20,"ETH":0.15,"SOL":0.10,"AVAX":0.10},
     "params":{"mu":0.0025,"sigma":0.022,"win_rate":0.52}},
    {"id":2,"name":"Mean Reversion","color":"#00e676","style":"Buy Dips / Sell Peaks",
     "description":"Assumes prices return to average. Buys oversold dips, sells overbought peaks. Works best in sideways/ranging markets.",
     "allocations":{"XRP":0.20,"XLM":0.20,"HBAR":0.20,"ETH":0.20,"BNB":0.10,"LINK":0.10},
     "params":{"mu":0.0018,"sigma":0.012,"win_rate":0.58}},
    {"id":3,"name":"Breakout","color":"#ffd740","style":"Catch Big Moves",
     "description":"Waits for price to break key levels, then enters for the big move. Fewer trades but aims for large gains. Higher risk/reward.",
     "allocations":{"XRP":0.10,"XLM":0.10,"HBAR":0.10,"BTC":0.20,"SOL":0.15,"INJ":0.10,"ARB":0.15,"SUI":0.10},
     "params":{"mu":0.0035,"sigma":0.030,"win_rate":0.45}},
    {"id":4,"name":"Multi-Factor Swing","color":"#b388ff","style":"Combined Signals",
     "description":"Combines RSI, MACD, volume and sentiment into one score before entering. Most conservative — only trades when multiple factors align.",
     "allocations":{"XRP":0.15,"XLM":0.15,"HBAR":0.15,"BTC":0.15,"ETH":0.15,"SOL":0.10,"LINK":0.15},
     "params":{"mu":0.0022,"sigma":0.016,"win_rate":0.55}},
]

# Detailed trade reasons per strategy
TRADE_REASONS = {
    1: { # Momentum
        "BUY":  ["RSI crossed above 50 — momentum building",
                 "Price broke above 20-day EMA — trend confirmed",
                 "MACD histogram turning positive — bulls in control",
                 "Volume spike on up day — institutional buying",
                 "Golden cross formed — strong trend signal"],
        "SELL": ["RSI dropped below 50 — momentum fading",
                 "Price fell below 20-day EMA — trend broken",
                 "MACD crossover bearish — momentum reversal",
                 "Lower high formed — uptrend structure broken",
                 "Volume dried up — buyers exhausted"],
    },
    2: { # Mean Reversion
        "BUY":  ["RSI hit 28 — deep oversold, statistically cheap",
                 "Price touched lower Bollinger Band — reversal likely",
                 "3-day losing streak — mean reversion setup",
                 "Stochastic oversold at 15 — bounce expected",
                 "Price 2 standard deviations below mean — high-probability buy"],
        "SELL": ["RSI reached 72 — overbought, mean reversion sell",
                 "Price hit upper Bollinger Band — fade the move",
                 "3-day winning streak — profit taking level",
                 "Stochastic overbought at 85 — pullback expected",
                 "Price 2 standard deviations above mean — high-probability sell"],
    },
    3: { # Breakout
        "BUY":  ["Price broke 30-day resistance with volume — breakout confirmed",
                 "Consolidation pattern resolved upward — big move starting",
                 "ATH breakout — no overhead resistance remaining",
                 "Flag pattern breakout — continuation move expected",
                 "Volume 3x average on breakout candle — conviction move"],
        "SELL": ["Breakout failed — price returned below resistance",
                 "Target reached — taking profit at 2x entry move",
                 "Stop hit — breakout did not follow through",
                 "Reversal candle at resistance — failed breakout",
                 "Volume faded after breakout — weak follow-through"],
    },
    4: { # Multi-Factor
        "BUY":  ["6/8 factors aligned bullish — high conviction entry",
                 "RSI + MACD + OBV all bullish simultaneously",
                 "Sentiment positive + on-chain accumulation detected",
                 "Technical score 7.8/10 — strongest signal in 2 weeks",
                 "All timeframes aligned — daily/4h/1h all bullish"],
        "SELL": ["Score dropped to 3/8 — bull case deteriorating",
                 "RSI divergence + MACD cross — dual warning signal",
                 "On-chain distribution detected — smart money selling",
                 "Technical score fell to 2.5/10 — exit triggered",
                 "Conflicting signals resolved bearish — cutting position"],
    },
}

COIN_PRICES = {
    "BTC":67600,"ETH":1957,"XRP":1.35,"XLM":0.22,"HBAR":0.14,
    "SOL":85,"BNB":629,"AVAX":15.5,"LINK":10.2,"INJ":9.50,
    "ARB":0.38,"SUI":1.85,"ADA":0.58,"DOT":3.80,"DOGE":0.095
}

def _pick_reason(strategy_id, action):
    reasons = TRADE_REASONS.get(strategy_id, TRADE_REASONS[1])
    pool = reasons.get(action, reasons["BUY"])
    return random.choice(pool)

def _trade_summary(strategy_id, trades, history=None):
    """Full performance scorecard including Sortino, R:R, weekly buckets, coin heatmap."""
    wins   = [t for t in trades if t["won"]]
    losses = [t for t in trades if not t["won"]]
    total_pnl = sum(t["pnl"] for t in trades)
    avg_win   = sum(t["pnl"] for t in wins)  / len(wins)   if wins   else 0
    avg_loss  = abs(sum(t["pnl"] for t in losses)) / len(losses) if losses else 0

    # R:R ratio
    rr_ratio = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0

    # Best / worst trades
    best  = max(trades, key=lambda t: t["pnl"]) if trades else None
    worst = min(trades, key=lambda t: t["pnl"]) if trades else None

    # Most traded coin
    coin_counts = {}
    for t in trades:
        coin_counts[t["coin"]] = coin_counts.get(t["coin"], 0) + 1
    top_coin = max(coin_counts, key=coin_counts.get) if coin_counts else "N/A"
    top_coin_wins  = len([t for t in trades if t["coin"]==top_coin and t["won"]])
    top_coin_total = coin_counts.get(top_coin, 0)

    # Win streak
    max_streak = cur_streak = 0
    for t in trades:
        if t["won"]: cur_streak += 1; max_streak = max(max_streak, cur_streak)
        else: cur_streak = 0

    # ── Sortino ratio (uses downside deviation only) ──────────────────────────
    sortino = 0.0
    if history:
        rets = [h["return_pct"] / 100 for h in history]
        neg_rets = [r for r in rets if r < 0]
        if neg_rets and len(rets) > 1:
            import math
            avg_ret  = sum(rets) / len(rets)
            downside = math.sqrt(sum(r**2 for r in neg_rets) / len(rets))
            sortino  = round((avg_ret / downside) * (252**0.5), 2) if downside > 0 else 0.0

    # ── Sharpe ratio ──────────────────────────────────────────────────────────
    sharpe = 0.0
    if history and len(history) > 1:
        import math
        rets    = [h["return_pct"] / 100 for h in history]
        avg_r   = sum(rets) / len(rets)
        std_r   = math.sqrt(sum((r - avg_r)**2 for r in rets) / (len(rets)-1))
        sharpe  = round((avg_r / std_r) * (252**0.5), 2) if std_r > 0 else 0.0

    # ── Weekly performance buckets (W1-W4) ───────────────────────────────────
    weekly = {}
    if history:
        for i, week_label in enumerate(["W1","W2","W3","W4"]):
            start = i * 7
            end   = min(start + 7, len(history))
            chunk = history[start:end]
            if len(chunk) >= 2:
                w_start = chunk[0]["value"]
                w_end   = chunk[-1]["value"]
                pct     = round((w_end - w_start) / w_start * 100, 1)
                weekly[week_label] = {"pct": pct, "start": w_start, "end": w_end}

    # ── Coin × Strategy heatmap data ─────────────────────────────────────────
    coin_perf = {}
    for t in trades:
        c = t["coin"]
        if c not in coin_perf:
            coin_perf[c] = {"wins": 0, "losses": 0, "pnl": 0.0, "trades": 0}
        coin_perf[c]["wins"]   += int(t["won"])
        coin_perf[c]["losses"] += int(not t["won"])
        coin_perf[c]["pnl"]    += t["pnl"]
        coin_perf[c]["trades"] += 1

    # Grade each coin: A+ / A / B / C / D
    def grade(wr, pnl):
        if wr >= 0.65 and pnl > 20: return "A+"
        if wr >= 0.55 and pnl > 10: return "A"
        if wr >= 0.45 and pnl > 0:  return "B"
        if wr >= 0.40:               return "C"
        return "D"

    for c, d in coin_perf.items():
        total = d["wins"] + d["losses"]
        wr    = d["wins"] / total if total else 0
        d["win_rate"] = round(wr * 100, 0)
        d["pnl"]      = round(d["pnl"], 2)
        d["grade"]    = grade(wr, d["pnl"])

    return {
        "total_pnl":       round(total_pnl, 2),
        "avg_win":         round(avg_win, 2),
        "avg_loss":        round(avg_loss, 2),
        "rr_ratio":        rr_ratio,
        "sortino":         sortino,
        "sharpe":          sharpe,
        "best_trade":      best,
        "worst_trade":     worst,
        "top_coin":        top_coin,
        "top_coin_record": f"{top_coin_wins}W/{top_coin_total-top_coin_wins}L",
        "max_win_streak":  max_streak,
        "total_trades":    len(trades),
        "wins":            len(wins),
        "losses":          len(losses),
        "weekly":          weekly,
        "coin_perf":       coin_perf,
    }

COMP_START = datetime(2026, 3, 1)
COMP_END   = datetime(2026, 3, 28)

def generate_competition_data(days: int = 28) -> dict:
    # Fixed seed so results are identical on every page load
    random.seed(99)
    np.random.seed(99)
    all_history = {}
    all_trades  = {}
    all_summaries = {}

    for s in STRATEGIES:
        p = s["params"]
        value = 500.0
        peak  = 500.0
        history = []
        trades  = []

        for day in range(days):
            date = (COMP_START + timedelta(days=day)).strftime("%Y-%m-%d")
            ret   = float(np.random.normal(p["mu"], p["sigma"]))
            value *= (1 + ret)
            peak  = max(peak, value)
            dd    = (peak - value) / peak * 100

            n = random.randint(0, 3)
            for _ in range(n):
                coin   = random.choice(list(s["allocations"].keys()))
                won    = random.random() < p["win_rate"]
                pnl    = float(random.uniform(3, 32) if won else random.uniform(-16, -2))
                action = "BUY" if random.random() > 0.3 else "SELL"
                reason = _pick_reason(s["id"], action)
                alloc  = s["allocations"].get(coin, 0.10)
                base_price = COIN_PRICES.get(coin, 1.0)
                entry_price = base_price * (1 + random.uniform(-0.05, 0.05))
                exit_price  = entry_price * (1 + (pnl / (500 * alloc))) if alloc > 0 else entry_price

                # Hold time varies by strategy
                hold_hours = {1: random.randint(4,24), 2: random.randint(2,12),
                              3: random.randint(12,72), 4: random.randint(6,36)}[s["id"]]

                # Entry and exit times
                entry_hour = random.randint(0, 23)
                entry_min  = random.randint(0, 59)
                exit_hour  = (entry_hour + hold_hours) % 24
                exit_min   = random.randint(0, 59)
                exit_date  = date
                if (entry_hour + hold_hours) >= 24:
                    d = datetime.strptime(date, "%Y-%m-%d") + timedelta(days=(entry_hour+hold_hours)//24)
                    exit_date = d.strftime("%Y-%m-%d")

                # Stop loss and take profit levels
                atr_pct = {"1":0.022,"2":0.012,"3":0.030,"4":0.016}.get(str(s["id"]),0.020)
                stop_loss   = round(entry_price * (1 - atr_pct * 1.2), 6)
                take_profit1 = round(entry_price * (1 + atr_pct * 1.5), 6)
                take_profit2 = round(entry_price * (1 + atr_pct * 3.0), 6)

                trades.append({
                    "date":         date,
                    "coin":         coin,
                    "action":       action,
                    "pnl":          round(pnl, 2),
                    "won":          won,
                    "reason":       reason,
                    "entry_price":  round(entry_price, 6),
                    "exit_price":   round(exit_price, 6),
                    "entry_time":   f"{entry_hour:02d}:{entry_min:02d}",
                    "exit_time":    f"{exit_hour:02d}:{exit_min:02d}",
                    "exit_date":    exit_date,
                    "hold_hours":   hold_hours,
                    "allocation":   round(alloc * 100, 0),
                    "stop_loss":    stop_loss,
                    "take_profit1": take_profit1,
                    "take_profit2": take_profit2,
                })

            history.append({"date":date,"value":round(value,2),
                            "return_pct":round(ret*100,3),"drawdown":round(dd,2)})

        all_history[str(s["id"])]   = history
        all_trades[str(s["id"])]    = trades
        all_summaries[str(s["id"])] = _trade_summary(s["id"], trades, history)

    # Coin price history
    coin_history = {}
    for sym, base in COIN_PRICES.items():
        prices = [base]
        vol = {"BTC":0.035,"ETH":0.045,"XRP":0.055,"XLM":0.068,"HBAR":0.075}.get(sym,0.060)
        for _ in range(days-1):
            prices.append(prices[-1]*(1+float(np.random.normal(0.001,vol*0.3))))
        coin_history[sym] = [round(p,6) for p in prices]

    # ── Correlation matrix between strategy equity curves ────────────────────
    import math
    def _corr(a, b):
        n = len(a)
        if n < 2: return 0.0
        ma, mb = sum(a)/n, sum(b)/n
        num    = sum((a[i]-ma)*(b[i]-mb) for i in range(n))
        sa     = math.sqrt(sum((x-ma)**2 for x in a))
        sb     = math.sqrt(sum((x-mb)**2 for x in b))
        return round(num/(sa*sb), 3) if sa*sb > 0 else 1.0

    ids   = [str(s["id"]) for s in STRATEGIES]
    names = [s["name"] for s in STRATEGIES]
    rets  = {sid: [h["return_pct"] for h in all_history[sid]] for sid in ids}
    corr_matrix = {}
    for i, si in enumerate(ids):
        corr_matrix[si] = {}
        for j, sj in enumerate(ids):
            corr_matrix[si][sj] = 1.0 if si == sj else _corr(rets[si], rets[sj])

    return {
        "strategies":    [{k:v for k,v in s.items() if k!="params"} for s in STRATEGIES],
        "history":       all_history,
        "trades":        all_trades,
        "summaries":     all_summaries,
        "coin_history":  coin_history,
        "corr_matrix":   corr_matrix,
        "strategy_names":names,
        "days":          days,
        "start_date":  COMP_START.strftime("%Y-%m-%d"),
        "end_date":    COMP_END.strftime("%Y-%m-%d"),
        "generated_at":datetime.now().isoformat(),
    }
