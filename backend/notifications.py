"""
CryptoSense AI — Notification Engine
Telegram (primary) with SMS fallback via Twilio
"""
import os
import json
import urllib.request
import urllib.parse
from datetime import datetime

SIGNAL_THRESHOLD = 8.0   # raised from 7.5 — only strong calls get alerts

STRATEGY_NAMES = {
    "1": "Momentum",
    "2": "Mean Reversion",
    "3": "Breakout",
    "4": "Multi-Factor",
}

# ── Telegram ──────────────────────────────────────────────────────────────────
def _tg_config():
    return {
        "token":   os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        "chat_id": os.environ.get("TELEGRAM_CHAT_ID", ""),
    }

def _tg_configured():
    cfg = _tg_config()
    return bool(cfg["token"] and cfg["chat_id"])

def format_telegram(signal: dict) -> str:
    """Rich Telegram message with model name and markdown formatting."""
    sym      = signal.get("symbol", "?")
    action   = signal.get("action", "?")
    conf     = signal.get("confidence", 0)
    entry    = signal.get("entry_price", 0)
    target   = signal.get("target_1", 0)
    stop     = signal.get("stop_loss", 0)
    rr       = signal.get("risk_reward", 0)
    reasons  = signal.get("top_reasons", [])
    strength = signal.get("signal_strength", "")
    model_id = str(signal.get("model_id", signal.get("strategy_id", "")))
    model    = STRATEGY_NAMES.get(model_id, "Multi-Factor")

    def fp(p):
        return f"${p:.2f}" if p >= 1 else f"${p:.4f}"

    emoji     = "🟢" if action == "BUY" else "🔴" if action == "SELL" else "🟡"
    conf_bar  = "█" * int(conf) + "░" * (10 - int(conf))

    breakout_keywords = ["breakout","broke","resistance","volume spike","flag pattern","consolidation"]
    is_breakout = any(kw in " ".join(reasons).lower() for kw in breakout_keywords)
    urgency_header = "⚡ *ACT WITHIN 30 MIN — BREAKOUT ENTRY*\n\n" if is_breakout else ""

    reasons_text = ""
    for i, r in enumerate(reasons[:3], 1):
        reasons_text += f"\n  {i}. {r}"

    target2 = signal.get("target_2", round(entry + (target - entry) * 2, 6))
    def fp2(p): return f"${p:.2f}" if p >= 1 else f"${p:.4f}"

    cb_sym = sym.lower()
    coinbase_url = f"https://www.coinbase.com/price/{cb_sym}"

    msg = (
        f"{urgency_header}"
        f"{emoji} *{action} {sym}* — Confidence: {conf}/10\n"
        f"`{conf_bar}`\n\n"
        f"🤖 *Model:* {model}\n"
        f"💰 *Entry:* {fp(entry)}\n"
        f"🎯 *TP1 — sell half:* {fp(target)}  _(lock in gains)_\n"
        f"🎯 *TP2 — sell rest:* {fp2(target2)}\n"
        f"🛑 *Stop loss:* {fp(stop)}  _(set immediately after buy)_\n"
        f"⚖️ *R/R:* {rr}x  |  *Strength:* {strength}\n\n"
        f"📋 *Why this signal fired:*{reasons_text}\n\n"
        f"{'⚠️ _If price already moved 3%+ from entry — skip this trade._' + chr(10) if is_breakout else ''}"
        f"[👉 Trade on Coinbase]({coinbase_url})\n"
        f"_CryptoSense AI · {model} · {datetime.now().strftime('%H:%M UTC')}_"
    )
    return msg


def format_pm_alert(market: dict) -> str:
    """Format a Kalshi prediction market opportunity alert."""
    title     = market.get("title", "Unknown market")
    side      = market.get("best_side", "YES")
    price     = market.get("best_price", 0)
    edge      = market.get("best_edge", 0)
    fair      = market.get("fair_value", 0)
    odds      = market.get("odds", 0)
    cat       = market.get("category", "other").title()
    days_left = market.get("days_left", 999)
    bet_size  = market.get("bet_size", 0)
    url       = market.get("url", "https://kalshi.com")

    side_emoji = "✅" if side == "YES" else "❌"
    priceCents = round(price * 100)
    fairCents  = round(fair * 100)
    edgePct    = round(edge * 100, 1)
    days_str   = f"{days_left}d left" if days_left < 999 else "long-dated"

    return (
        f"🎲 *Kalshi PM Opportunity*\n\n"
        f"📌 *{title}*\n\n"
        f"{side_emoji} *Bet {side}* at {priceCents}¢  _(fair value: {fairCents}¢)_\n"
        f"📈 Edge: *+{edgePct}%* above fair value\n"
        f"💰 Suggested bet: *${bet_size:.0f}* (half-Kelly)\n"
        f"🎯 Payout: *{odds:.1f}x* on resolution\n"
        f"🏷️ Category: {cat}  |  {days_str}\n\n"
        f"[👉 Bet on Kalshi]({url})\n"
        f"_CryptoSense AI · Kalshi Scanner · {datetime.now().strftime('%H:%M UTC')}_"
    )


def send_telegram(signal: dict) -> dict:
    """Send a Telegram message for a signal."""
    if not _tg_configured():
        return {"sent": False,
                "message": "Telegram not configured — add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in Render",
                "platform": "telegram"}

    if signal.get("confidence", 0) < SIGNAL_THRESHOLD:
        return {"sent": False,
                "message": f"Confidence {signal.get('confidence')} below threshold {SIGNAL_THRESHOLD}",
                "platform": "telegram"}
    try:
        cfg  = _tg_config()
        text = format_telegram(signal)
        url  = f"https://api.telegram.org/bot{cfg['token']}/sendMessage"
        payload = json.dumps({
            "chat_id":    cfg["chat_id"],
            "text":       text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False,
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            result = json.loads(resp.read())
        if result.get("ok"):
            return {"sent": True, "message": "Telegram message sent", "platform": "telegram"}
        else:
            return {"sent": False, "message": str(result), "platform": "telegram"}
    except Exception as e:
        return {"sent": False, "message": str(e), "platform": "telegram"}


def send_telegram_text(text: str) -> dict:
    """Send a raw text message to Telegram (for summaries, alerts, heartbeats)."""
    if not _tg_configured():
        return {"sent": False, "message": "Telegram not configured"}
    try:
        cfg = _tg_config()
        url = f"https://api.telegram.org/bot{cfg['token']}/sendMessage"
        payload = json.dumps({
            "chat_id":    cfg["chat_id"],
            "text":       text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            result = json.loads(resp.read())
        return {"sent": result.get("ok", False), "message": "OK" if result.get("ok") else str(result)}
    except Exception as e:
        return {"sent": False, "message": str(e)}


def send_pm_alert(market: dict) -> dict:
    """Send a Kalshi prediction market alert to Telegram."""
    if not _tg_configured():
        return {"sent": False, "message": "Telegram not configured", "platform": "telegram"}
    try:
        cfg  = _tg_config()
        text = format_pm_alert(market)
        url  = f"https://api.telegram.org/bot{cfg['token']}/sendMessage"
        payload = json.dumps({
            "chat_id":    cfg["chat_id"],
            "text":       text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False,
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            result = json.loads(resp.read())
        if result.get("ok"):
            return {"sent": True, "message": "PM alert sent", "platform": "telegram"}
        else:
            return {"sent": False, "message": str(result), "platform": "telegram"}
    except Exception as e:
        return {"sent": False, "message": str(e), "platform": "telegram"}


# ── SMS fallback via Twilio ───────────────────────────────────────────────────
def _sms_configured():
    return all([
        os.environ.get("TWILIO_ACCOUNT_SID"),
        os.environ.get("TWILIO_AUTH_TOKEN"),
        os.environ.get("TWILIO_FROM_NUMBER"),
        os.environ.get("TWILIO_TO_NUMBER"),
    ])

def send_sms(signal: dict) -> dict:
    """SMS fallback — only used if Telegram is not configured."""
    if not _sms_configured():
        return {"sent": False, "message": "SMS not configured", "platform": "sms"}
    try:
        from twilio.rest import Client
        sym    = signal.get("symbol","?")
        action = signal.get("action","?")
        conf   = signal.get("confidence",0)
        entry  = signal.get("entry_price",0)
        target = signal.get("target_1",0)
        stop   = signal.get("stop_loss",0)
        rr     = signal.get("risk_reward",0)
        reasons = signal.get("top_reasons",[])
        model_id = str(signal.get("model_id", signal.get("strategy_id", "")))
        model    = STRATEGY_NAMES.get(model_id, "Multi-Factor")
        def fp(p): return f"${p:.2f}" if p>=1 else f"${p:.4f}"
        reason_str = " + ".join(r.split("—")[0].strip() for r in reasons[:3])
        body = (f"CryptoSense AI [{model}]\n{action} {sym} Conf:{conf}/10\n"
                f"Entry:{fp(entry)} Target:{fp(target)} Stop:{fp(stop)}\n"
                f"R/R:{rr}x\nWhy: {reason_str}\n"
                f"coinbase.com/price/{sym.lower()}")
        client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
        msg = client.messages.create(
            body=body,
            from_=os.environ["TWILIO_FROM_NUMBER"],
            to=os.environ["TWILIO_TO_NUMBER"]
        )
        return {"sent": True, "message": "SMS sent", "platform": "sms", "sid": msg.sid}
    except Exception as e:
        return {"sent": False, "message": str(e), "platform": "sms"}


# ── Unified send ──────────────────────────────────────────────────────────────
def send_alert(signal: dict) -> dict:
    if _tg_configured():
        return send_telegram(signal)
    elif _sms_configured():
        return send_sms(signal)
    else:
        return {"sent": False, "message": "No notification method configured", "platform": "none"}

def _is_configured() -> bool:
    return _tg_configured() or _sms_configured()

def check_and_alert(signals: list) -> list:
    alerts = []
    for sig in signals:
        if sig.get("confidence", 0) >= SIGNAL_THRESHOLD:
            result = send_alert(sig)
            result["symbol"]     = sig.get("symbol")
            result["confidence"] = sig.get("confidence")
            alerts.append(result)
    return alerts

def format_sms(signal: dict) -> str:
    sym = signal.get("symbol","?")
    return f"CryptoSense: {signal.get('action')} {sym} Conf:{signal.get('confidence')}/10"


# ── Welcome message ───────────────────────────────────────────────────────────
WELCOME_MSG = """👋 *Welcome to CryptoSense AI Signals!*

Here's what you need to know:

1️⃣ Signals fire when confidence ≥ 8/10 — only strong setups get through

2️⃣ Each alert tells you:
   • Which model made the call (Momentum / Mean Reversion / Breakout / Multi-Factor)
   • What to buy and at what price
   • Where to set your *stop loss* (set this FIRST on Coinbase)
   • Two take profit targets — sell half at each

3️⃣ Hourly heartbeat — every hour on the hour:
   • 🟢 Signal alert if confidence ≥ 8/10
   • 🎲 Kalshi PM alert if edge ≥ 6%
   • 🔕 "No updates" if market is quiet

4️⃣ Breakout signals marked ⚡ — act within 30 min or skip the trade

5️⃣ These are AI-generated signals, *not financial advice*. Always size positions responsibly.

📌 Read the pinned message before your first trade.

Good luck! 🚀
_— CryptoSense AI_"""


def send_welcome(new_member_name: str = None) -> dict:
    if not _tg_configured():
        return {"sent": False, "message": "Telegram not configured"}
    try:
        cfg = _tg_config()
        greeting = f"👋 Welcome, *{new_member_name}*!\n\n" if new_member_name else ""
        text = greeting + WELCOME_MSG
        url = f"https://api.telegram.org/bot{cfg['token']}/sendMessage"
        payload = json.dumps({
            "chat_id":    cfg["chat_id"],
            "text":       text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            result = json.loads(resp.read())
        if result.get("ok"):
            return {"sent": True, "message": "Welcome message sent"}
        else:
            return {"sent": False, "message": str(result)}
    except Exception as e:
        return {"sent": False, "message": str(e)}
