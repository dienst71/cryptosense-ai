"""CryptoSense AI — Sentiment & On-Chain Engine"""
import numpy as np
import random
from datetime import datetime, timedelta

BULLISH = ["{c} surges as institutional demand hits record levels",
           "Major payment processor integrates {c} for global settlements",
           "{c} network activity reaches all-time high",
           "{c} whale accumulation hits 6-month high",
           "Analysts raise {c} price target as adoption accelerates"]
BEARISH = ["{c} faces selling pressure amid regulatory uncertainty",
           "Large {c} wallet moves funds to exchange",
           "{c} drops below key moving average as volume fades",
           "Market analyst warns of {c} overbought conditions"]
NEUTRAL = ["{c} consolidates near support ahead of major upgrade",
           "{c} trading volume steady as market awaits catalyst",
           "{c} developers release updated roadmap"]

def get_sentiment_score(symbol: str) -> dict:
    score = float(np.clip(np.random.normal(0.25, 0.4), -1.0, 1.0))
    pool = BULLISH if score>0.3 else BEARISH if score<-0.3 else NEUTRAL
    news = []
    for t in random.sample(pool, min(3, len(pool))):
        news.append({
            "headline": t.replace("{c}", symbol),
            "sentiment": round(score + np.random.normal(0, 0.1), 3),
            "source": random.choice(["CoinDesk","Decrypt","The Block","Cointelegraph"]),
            "time": (datetime.now()-timedelta(minutes=random.randint(10,240))).strftime("%H:%M"),
        })
    return {
        "symbol": symbol,
        "score": round(score, 4),
        "label": "Bullish" if score>0.2 else "Bearish" if score<-0.2 else "Neutral",
        "mention_volume": int(abs(np.random.normal(1500, 600))),
        "twitter_mentions": int(abs(np.random.normal(3500, 1500))),
        "recent_news": news,
        "timestamp": datetime.now().isoformat(),
    }

def get_onchain_metrics(symbol: str) -> dict:
    flow = float(np.random.normal(-200, 800))
    funding = round(float(np.random.normal(0.01, 0.035)), 4)
    return {
        "symbol": symbol,
        "exchange_flow_btc": round(flow, 2),
        "exchange_flow_label": "Net Outflow (Bullish)" if flow<-100 else "Net Inflow (Bearish)" if flow>100 else "Neutral",
        "whale_activity": "Accumulating" if flow<0 else "Distributing",
        "whale_transactions": int(abs(np.random.normal(45, 20))),
        "funding_rate": funding,
        "funding_signal": "Longs Overheated" if funding>0.05 else "Shorts Overheated" if funding<-0.03 else "Balanced",
        "open_interest_change_24h": round(float(np.random.normal(2.5, 8.0)), 2),
        "active_addresses": int(abs(np.random.normal(950000, 150000))),
        "address_trend": "Rising" if np.random.random()>0.35 else "Falling",
        "long_pct": round(float(np.clip(np.random.normal(55, 8), 30, 75)), 1),
        "network_health_score": round(float(np.clip(np.random.normal(68, 15), 20, 95)), 1),
    }
