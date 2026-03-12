"""
CryptoSense AI — Signal Generation Engine
Each signal includes exactly 3 plain-English reasons why
"""
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime
from typing import List


@dataclass
class TradingSignal:
    symbol: str
    action: str
    confidence: float
    entry_price: float
    target_1: float
    target_2: float
    stop_loss: float
    risk_reward: float
    position_size_pct: float
    time_horizon: str
    top_reasons: List[str]        # exactly 3 plain-English reasons
    score_breakdown: dict          # full scoring transparency
    technical_basis: str
    sentiment_factor: str
    onchain_signal: str
    key_risk: str
    invalidation_level: float
    market_context: str
    signal_strength: str
    timestamp: str


# ── Scoring weights ───────────────────────────────────────────────────────────
SCORE_RULES = {
    # (condition_fn, bull_pts, bear_pts, label_bull, label_bear)
    "rsi_oversold":    ("RSI oversold ({v:.0f}) — buying pressure likely",    0.30, 0.00),
    "rsi_overbought":  ("RSI overbought ({v:.0f}) — selling pressure likely", 0.00, 0.30),
    "rsi_bullish":     ("RSI in bullish momentum zone ({v:.0f})",             0.10, 0.00),
    "macd_bull_cross": ("MACD bullish crossover — momentum shifting up",      0.25, 0.00),
    "macd_bear_cross": ("MACD bearish crossover — momentum shifting down",    0.00, 0.25),
    "macd_bullish":    ("MACD histogram positive — upward momentum",          0.10, 0.00),
    "macd_bearish":    ("MACD histogram negative — downward momentum",        0.00, 0.10),
    "golden_cross":    ("Golden cross — short-term EMA crossed above long",   0.20, 0.00),
    "death_cross":     ("Death cross — short-term EMA crossed below long",    0.00, 0.20),
    "ema_above":       ("Price above key EMAs — uptrend structure intact",    0.10, 0.00),
    "ema_below":       ("Price below key EMAs — downtrend structure intact",  0.00, 0.10),
    "bb_low":          ("Near lower Bollinger Band — statistically cheap",    0.20, 0.00),
    "bb_high":         ("Near upper Bollinger Band — statistically expensive",0.00, 0.20),
    "sar_bull":        ("Parabolic SAR bullish — trend support below price",  0.08, 0.00),
    "sar_bear":        ("Parabolic SAR bearish — trend resistance above",     0.00, 0.08),
    "obv_rising":      ("OBV rising — volume confirms buying",               0.10, 0.00),
    "obv_falling":     ("OBV falling — volume confirms selling",             0.00, 0.10),
    "pattern_bull":    ("Bullish candlestick pattern detected",              0.12, 0.00),
    "pattern_bear":    ("Bearish candlestick pattern detected",              0.00, 0.12),
    "outflow":         ("Exchange outflows — coins moving to wallets (bullish)",0.15,0.00),
    "inflow":          ("Exchange inflows — coins moving to exchanges (bearish)",0.00,0.15),
    "accumulation":    ("Whale accumulation detected on-chain",              0.10, 0.00),
    "distribution":    ("Whale distribution detected on-chain",              0.00, 0.10),
    "sentiment_bull":  ("Market sentiment positive — crowd leaning bullish", 0.10, 0.00),
    "sentiment_bear":  ("Market sentiment negative — crowd leaning bearish", 0.00, 0.10),
    "bull_regime":     ("Market in bullish trending regime",                 0.10, 0.00),
    "bear_regime":     ("Market in bearish trending regime",                 0.00, 0.10),
}


def generate_signal(symbol, current_price, indicators, patterns, sentiment,
                    onchain, support_levels, resistance_levels,
                    market_regime, price_change_24h=0.0) -> TradingSignal:

    rsi  = indicators.get("rsi_14", 50)
    mb   = indicators.get("macd_bias", "")
    ec   = indicators.get("ema_cross", "")
    bb   = indicators.get("bb_position", 0.5)
    sar  = indicators.get("sar_signal", "")
    obv  = indicators.get("obv_trend", "")
    sent = sentiment.get("score", 0.0)
    flow = onchain.get("exchange_flow_label", "")
    whal = onchain.get("whale_activity", "")

    # ── Score every factor ────────────────────────────────────────────────────
    bull_score = 0.0
    bear_score = 0.0
    scored = []   # list of (net_pts, label) for transparency

    def score(pts_b, pts_bear, label):
        nonlocal bull_score, bear_score
        bull_score += pts_b
        bear_score += pts_bear
        net = pts_b - pts_bear
        scored.append((net, label))

    if rsi < 30:
        score(0.30, 0, f"RSI oversold at {rsi:.0f} — historically strong buy zone")
    elif rsi > 70:
        score(0, 0.30, f"RSI overbought at {rsi:.0f} — historically strong sell zone")
    elif 45 < rsi < 60:
        score(0.10, 0, f"RSI at {rsi:.0f} — healthy bullish momentum zone")

    if "Bullish Crossover" in mb:
        score(0.25, 0, "MACD bullish crossover — momentum just shifted upward")
    elif "Bearish Crossover" in mb:
        score(0, 0.25, "MACD bearish crossover — momentum just shifted downward")
    elif mb == "Bullish":
        score(0.10, 0, "MACD histogram positive — sustained upward momentum")
    elif mb == "Bearish":
        score(0, 0.10, "MACD histogram negative — sustained downward momentum")

    if "Golden" in ec:
        score(0.20, 0, "Golden cross — fast EMA crossed above slow EMA")
    elif "Death" in ec:
        score(0, 0.20, "Death cross — fast EMA crossed below slow EMA")
    elif "Above" in ec:
        score(0.10, 0, "Price above EMA — uptrend structure intact")
    elif "Below" in ec:
        score(0, 0.10, "Price below EMA — downtrend structure intact")

    if bb < 0.10:
        score(0.20, 0, "Near lower Bollinger Band — price statistically cheap")
    elif bb > 0.90:
        score(0, 0.20, "Near upper Bollinger Band — price statistically expensive")

    if sar == "Bullish":
        score(0.08, 0, "Parabolic SAR bullish — trend support confirmed below price")
    else:
        score(0, 0.08, "Parabolic SAR bearish — trend resistance above price")

    if obv == "Rising":
        score(0.10, 0, "OBV rising — volume confirms buying activity")
    else:
        score(0, 0.10, "OBV falling — volume confirms selling activity")

    for p in patterns:
        if p.get("direction") == "bullish":
            score(p.get("confidence", 0.5) * 0.15, 0,
                  f"{p['name']} pattern — bullish candlestick signal")
        elif p.get("direction") == "bearish":
            score(0, p.get("confidence", 0.5) * 0.15,
                  f"{p['name']} pattern — bearish candlestick signal")

    if "Outflow" in flow:
        score(0.15, 0, "Exchange outflows — investors moving coins off exchanges (bullish)")
    elif "Inflow" in flow:
        score(0, 0.15, "Exchange inflows — investors moving coins onto exchanges (bearish)")

    if whal == "Accumulating":
        score(0.10, 0, "Whale wallets accumulating — large holders buying")
    else:
        score(0, 0.10, "Whale wallets distributing — large holders selling")

    if sent > 0.2:
        score(0.10, 0, f"Positive sentiment score ({sent:+.2f}) — crowd leaning bullish")
    elif sent < -0.2:
        score(0, 0.10, f"Negative sentiment score ({sent:+.2f}) — crowd leaning bearish")

    if "Bull" in market_regime:
        score(0.10, 0, f"Market regime: {market_regime} — macro tailwind")
    elif "Bear" in market_regime:
        score(0, 0.10, f"Market regime: {market_regime} — macro headwind")

    # ── Determine action ──────────────────────────────────────────────────────
    net   = bull_score - bear_score
    total = float(np.clip(net * 0.6, -1.0, 1.0))

    if total > 0.20:
        action = "BUY"
        # Top 3 reasons = highest-scoring bull factors
        top3 = [label for pts, label in sorted(scored, reverse=True) if pts > 0][:3]
    elif total < -0.20:
        action = "SELL"
        top3 = [label for pts, label in sorted(scored) if pts < 0][:3]
    else:
        action = "HOLD"
        top3 = [label for _, label in sorted(scored, key=lambda x: abs(x[0]), reverse=True)][:3]

    # Pad to exactly 3 if needed
    defaults = ["Mixed technical picture — no clear edge",
                "Waiting for confirmation signal",
                "Risk/reward not favorable at current levels"]
    while len(top3) < 3:
        top3.append(defaults[len(top3) - 1])
    top3 = top3[:3]

    confidence = float(np.clip(5.0 + abs(total) * 5.0, 1.0, 10.0))

    # ── Regime-Strategy Suppression ───────────────────────────────────────────
    # The model assigned in app.py (_assign_model) maps to strategy types.
    # We apply confidence penalties here based on regime / strategy mismatch.
    # Regime signals are embedded in market_regime from the enhanced classifier.
    regime_penalty = 0.0
    regime_note = None

    if "Ranging" in market_regime or "Consolidating" in market_regime:
        # Ranging market: Momentum and Breakout strategies lose edge
        # Mean Reversion works well; Multi-Factor neutral
        if action == "BUY":
            # In ranging markets, breakout-style buys tend to fail
            regime_penalty = 1.2
            regime_note = f"⚠️ Ranging market (ADX weak) — breakout/momentum signals less reliable"
        # SELL in ranging = potential mean reversion = no penalty
    elif market_regime == "High Volatility":
        # All strategies get a penalty — high vol = high uncertainty
        regime_penalty = 0.8
        regime_note = f"⚠️ High volatility regime — all signals get uncertainty discount"
    elif market_regime == "Transitional":
        # ADX 20-25 zone — trending regime not yet confirmed
        regime_penalty = 0.5
        regime_note = f"⚠️ Transitional regime (ADX indeterminate) — wait for confirmation"
    elif "Trending" in market_regime:
        # Trending: Mean Reversion signals in a strong trend are the dangerous ones
        # Breakout and Momentum thrive — no penalty for those
        # We can't know strategy type yet (assigned after), so just log
        regime_note = None  # No penalty in trending — strategies aligned

    if regime_penalty > 0:
        confidence = float(np.clip(confidence - regime_penalty, 1.0, 10.0))
        if regime_note:
            top3.append(regime_note)
            top3 = top3[:3]  # keep capped at 3


    atr_v = indicators.get("atr_14", current_price * 0.02)
    ap    = atr_v / current_price if current_price > 0 else 0.02

    if action == "BUY":
        entry    = current_price
        target_1 = current_price * (1 + ap * 1.5)
        target_2 = current_price * (1 + ap * 3.0)
        stop     = current_price * (1 - ap * 1.2)
        inv      = stop * 0.995
        if resistance_levels:
            r = [r for r in resistance_levels if r > current_price]
            if r: target_1 = min(r[0], target_1 * 1.05)
        if support_levels:
            s = [s for s in support_levels if s < current_price]
            if s: stop = max(s[-1] * 0.99, stop)
    elif action == "SELL":
        entry    = current_price
        target_1 = current_price * (1 - ap * 1.5)
        target_2 = current_price * (1 - ap * 3.0)
        stop     = current_price * (1 + ap * 1.2)
        inv      = stop * 1.005
    else:
        entry    = current_price
        target_1 = current_price * (1 + ap * 2.0)
        target_2 = current_price * (1 + ap * 4.0)
        stop     = current_price * (1 - ap * 2.0)
        inv      = stop

    gain = abs(target_1 - entry)
    loss = abs(stop - entry)
    rr   = round(gain / loss, 2) if loss > 0 else 1.0

    pos_size = (float(np.random.uniform(4, 7)) if confidence >= 8 else
                float(np.random.uniform(2, 4)) if confidence >= 6 else
                float(np.random.uniform(0.5, 2)))

    horizon  = "1-2 hours" if confidence >= 8 else "2-4 hours" if confidence >= 6 else "4-8 hours"
    strength = "STRONG" if confidence >= 8 else "MODERATE" if confidence >= 6 else "WEAK"

    # Full score breakdown for transparency
    score_breakdown = {
        "bull_score":   round(bull_score, 3),
        "bear_score":   round(bear_score, 3),
        "net_score":    round(net, 3),
        "total":        round(total, 3),
        "factors_scored": len(scored),
        "all_factors":  [(round(pts,3), lbl) for pts, lbl in
                         sorted(scored, key=lambda x: abs(x[0]), reverse=True)],
    }

    return TradingSignal(
        symbol            = symbol,
        action            = action,
        confidence        = round(confidence, 1),
        entry_price       = round(entry, 6),
        target_1          = round(target_1, 6),
        target_2          = round(target_2, 6),
        stop_loss         = round(stop, 6),
        risk_reward       = rr,
        position_size_pct = round(pos_size, 1),
        time_horizon      = horizon,
        top_reasons       = top3,
        score_breakdown   = score_breakdown,
        technical_basis   = f"{top3[0]}. {market_regime} regime.",
        sentiment_factor  = f"Sentiment {sent:+.2f} ({sentiment.get('label','Neutral')})",
        onchain_signal    = ("Exchange outflows — accumulation." if "Outflow" in flow
                             else "Exchange inflows — caution."),
        key_risk          = ("Broader market reversal could invalidate this setup." if action == "BUY"
                             else "Sudden positive catalyst could squeeze position." if action == "SELL"
                             else "Breakout in either direction possible."),
        invalidation_level = round(inv, 6),
        market_context    = (f"{market_regime} | 24h: {price_change_24h:+.2f}% | "
                             f"Funding: {onchain.get('funding_rate', 0):.4f}"),
        signal_strength   = strength,
        timestamp         = datetime.now().isoformat(),
    )
