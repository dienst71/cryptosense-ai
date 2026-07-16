"""
CryptoSense AI — Flask API Server
Includes hourly background scanner for passive Telegram alerts
"""
import os, sys, threading, time
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, jsonify, send_from_directory
from dataclasses import asdict
import numpy as np

from market_data import generate_ohlcv, get_current_prices, get_fear_greed_index, COINS, get_coin_tier
from technical_analysis import analyze
from sentiment import get_sentiment_score, get_onchain_metrics
from signals import generate_signal
from strategy_engine import generate_competition_data
from kalshi import get_kalshi_markets
from notifications import (send_telegram, send_telegram_text, send_sms,
                            send_alert, check_and_alert, _is_configured,
                            _tg_configured, _sms_configured, send_welcome)
from flask import Flask, jsonify, send_from_directory, request
from signal_log import log_signal, log_kalshi, get_signals, get_kalshi_signals, get_stats, update_outcome, update_kalshi_outcome
from funding_rates import apply_funding_filter, refresh_funding_rates, funding_summary, get_all_rates, THRESHOLD_BLOCK
from momentum_scanner import scan_momentum, format_momentum_alert
from catalyst_calendar import get_upcoming_catalysts, get_catalyst_coins
from trump_tracker import run_trump_scan, get_recent_posts as get_trump_posts, get_stats as get_trump_stats, init_db as init_trump_db
from catalyst_calendar import get_upcoming_catalysts, get_catalyst_coins
from momentum_scanner import scan_momentum, format_momentum_alert

app = Flask(__name__)
FRONTEND = os.path.join(os.path.dirname(__file__), '..', 'frontend')

# ── Hourly background scanner ─────────────────────────────────────────────────
_last_scan_result = {"scanned": 0, "alerts_sent": 0, "last_run": None, "signals": []}
_last_heartbeat_sent = None     # tracks last successful Telegram send — dead man's switch
_execution_halted = False       # volatility circuit breaker flag
_halt_reason = ""               # reason for halt
_last_momentum_scan = None
_last_trump_scan = None
_last_momentum_scan = None

STRATEGY_NAMES = {"1":"Momentum","2":"Mean Reversion","3":"Breakout","4":"Multi-Factor"}

def _assign_model(signal: dict) -> dict:
    """Assign a model name to a signal based on its characteristics."""
    reasons = " ".join(signal.get("top_reasons", [])).lower()
    conf    = signal.get("confidence", 0)
    if any(k in reasons for k in ["breakout","broke","resistance","flag","consolidat"]):
        model_id = "3"
    elif any(k in reasons for k in ["oversold","overbought","mean","reversion","bollinger"]):
        model_id = "2"
    elif any(k in reasons for k in ["momentum","macd","trend","golden cross","ema"]):
        model_id = "1"
    else:
        model_id = "4"
    signal["model_id"]   = model_id
    signal["model_name"] = STRATEGY_NAMES[model_id]
    return signal

def _check_vol_circuit_breaker(prices: dict) -> tuple[bool, str]:
    """
    Volatility circuit breaker.
    Halts signal execution when BTC hourly volatility > 2x its 30-day average.
    Returns (halted: bool, reason: str)
    """
    try:
        btc_change = abs(prices.get("BTC", {}).get("change_24h", 0))
        # Proxy: if BTC 24h move > 12%, that's extreme vol (approx 2x normal ~6% daily)
        if btc_change > 12.0:
            return True, f"BTC 24h move {btc_change:.1f}% exceeds 12% threshold — circuit breaker active"
    except Exception:
        pass
    return False, ""


def _run_scan():
    """Scan all coins and send Telegram alerts for high-confidence signals."""
    global _last_scan_result, _last_heartbeat_sent, _execution_halted, _halt_reason
    import datetime as _dt

    now_dt  = _dt.datetime.now()
    now_str = now_dt.strftime('%H:%M UTC')
    date_str= now_dt.strftime('%a %b %-d')

    coins  = ['BTC','ETH','XRP','XLM','HBAR','SOL','BNB','AVAX','LINK','ARB','SUI','INJ','CHZ','PSG','BAR']
    prices = get_current_prices()

    # ── 1. Refresh funding rates ───────────────────────────────────────────────
    try:
        refresh_funding_rates()
    except Exception:
        pass

    # ── 2. Volatility circuit breaker check ───────────────────────────────────
    halted, halt_msg = _check_vol_circuit_breaker(prices)
    if halted and not _execution_halted:
        _execution_halted = True
        _halt_reason = halt_msg
        if _tg_configured():
            send_telegram_text(
                f"🚨 *CIRCUIT BREAKER TRIGGERED — {date_str} {now_str}*\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"⚠️ {halt_msg}\n\n"
                f"Signal execution is paused. Monitoring continues.\n"
                f"Will auto-resume when volatility normalises."
            )
    elif not halted and _execution_halted:
        _execution_halted = False
        _halt_reason = ""
        if _tg_configured():
            send_telegram_text(
                f"✅ *Circuit Breaker Cleared — {date_str} {now_str}*\n"
                f"Volatility has normalised. Signal execution resumed."
            )

    # ── 3. Generate signals with funding rate filter applied ──────────────────
    signals = []
    for sym in coins:
        try:
            df   = generate_ohlcv(sym, 300)
            ta   = analyze(sym, df)
            sent = get_sentiment_score(sym)
            oc   = get_onchain_metrics(sym)
            sig  = generate_signal(sym, ta['current_price'], ta['indicators'],
                                   ta['patterns'], sent, oc,
                                   ta['support_levels'], ta['resistance_levels'],
                                   ta['market_regime'], prices[sym].get('change_24h',0))
            s = asdict(sig)
            s = _assign_model(s)
            s = apply_funding_filter(s)   # ← funding rate adjustment
            s['coin_tier'] = get_coin_tier(sym)  # ← liquidity tier
            signals.append(s)
        except Exception:
            continue

    alerts      = check_and_alert(signals)
    high_conf   = [s for s in signals if s['confidence'] >= 8.0]
    alerts_sent = [a for a in alerts if a.get('sent')]

    # ── 4. Log every high-confidence signal to SQLite ─────────────────────────
    for s in high_conf:
        try:
            log_signal(s)
        except Exception:
            pass

    # ── 5. Kalshi PM scan ─────────────────────────────────────────────────────
    pm_alerts_sent = 0
    pm_opportunities = []
    kalshi_data = {}
    try:
        from kalshi import get_kalshi_markets
        from notifications import send_pm_alert
        kalshi_data = get_kalshi_markets(force_refresh=True)
        pm_opportunities = kalshi_data.get("recommended", [])
        for mkt in pm_opportunities:
            if mkt.get("best_edge", 0) >= 0.06:
                result = send_pm_alert(mkt)
                if result.get("sent"):
                    pm_alerts_sent += 1
                    try:
                        log_kalshi(mkt)
                    except Exception:
                        pass
    except Exception:
        pass

    # ── 6. Hourly heartbeat ───────────────────────────────────────────────────
    if _tg_configured():
        has_crypto = len(high_conf) > 0
        has_pm     = pm_alerts_sent > 0

        if _execution_halted:
            # Circuit breaker active — note it in heartbeat
            send_telegram_text(
                f"🚨 *Circuit Breaker ACTIVE — {date_str} {now_str}*\n"
                f"_Scanning but not executing. {_halt_reason}_"
            )
        elif has_crypto or has_pm:
            summary = f"🔍 *CryptoSense AI — {date_str} {now_str}*\n"
            summary += f"━━━━━━━━━━━━━━━━━━━━━\n"
            if has_crypto:
                summary += f"📊 *Crypto Signals* ({len(high_conf)} ≥ 8/10)\n"
                for s in sorted(high_conf, key=lambda x: x['confidence'], reverse=True):
                    emoji = "🟢" if s['action']=='BUY' else "🔴" if s['action']=='SELL' else "🟡"
                    model = s.get('model_name', 'Multi-Factor')
                    fr    = s.get('funding_rate')
                    fr_tag = f" · FR:{fr*100:.3f}%" if fr is not None else ""
                    flag  = s.get('funding_flag','')
                    flag_tag = " ⚠️" if flag in ('warning','extreme') else ""
                    tier  = s.get('coin_tier', 2)
                    tier_tag = " T1" if tier == 1 else " T2"
                    summary += f"{emoji} {s['action']} *{s['symbol']}*{tier_tag} {s['confidence']}/10 · _{model}_{fr_tag}{flag_tag}\n"
            if has_pm:
                summary += f"\n🎲 *Kalshi PM* ({pm_alerts_sent} high-edge alert{'s' if pm_alerts_sent>1 else ''} sent)\n"
                for m in pm_opportunities[:3]:
                    edge_pct = round(m.get('best_edge',0)*100,1)
                    summary += f"  • {m['title'][:50]} (+{edge_pct}%)\n"
            send_telegram_text(summary)
        else:
            send_telegram_text(
                f"🔕 *No Updates — {date_str} {now_str}*\n"
                f"Scanned {len(coins)} coins + {len(kalshi_data.get('recommended',[]))} PM markets\n"
                f"_No crypto signals ≥ 8/10. No PM edge ≥ 6%. Market is quiet._"
            )

        _last_heartbeat_sent = _dt.datetime.now()

    # Momentum scanner — runs every 15 min
    global _last_momentum_scan
    try:
        import datetime as _dt2
        if (_last_momentum_scan is None or
                (_dt2.datetime.now() - _last_momentum_scan).total_seconds() > 900):
            _last_momentum_scan = _dt2.datetime.now()
            mo_alerts = scan_momentum()
            if mo_alerts and _tg_configured():
                for coin in mo_alerts[:3]:
                    send_telegram_text(format_momentum_alert(coin))
    except Exception:
        pass

    global _last_momentum_scan
    try:
        import datetime as _dt2
        if (_last_momentum_scan is None or
                (_dt2.datetime.now() - _last_momentum_scan).total_seconds() > 900):
            _last_momentum_scan = _dt2.datetime.now()
            mo_alerts = scan_momentum()
            if mo_alerts and _tg_configured():
                for coin in mo_alerts[:3]:
                    send_telegram_text(format_momentum_alert(coin))
    except Exception:
        pass

    _last_scan_result = {
        "scanned":          len(coins),
        "alerts_sent":      len(alerts_sent),
        "pm_alerts_sent":   pm_alerts_sent,
        "last_run":         _dt.datetime.now().isoformat(),
        "signals":          sorted(high_conf, key=lambda x: x['confidence'], reverse=True),
        "circuit_breaker":  _execution_halted,
        "halt_reason":      _halt_reason,
    }

def _hourly_scheduler():
    """Run scan immediately on startup, then every hour."""
    time.sleep(10)  # wait 10s for app to fully start
    while True:
        try:
            _run_scan()
        except Exception:
            pass

        # ── Dead man's switch: alert if no heartbeat sent in 90 minutes ───────
        try:
            import datetime as _dt
            if _last_heartbeat_sent and _tg_configured():
                gap = (_dt.datetime.now() - _last_heartbeat_sent).total_seconds()
                if gap > 5400:  # 90 minutes
                    send_telegram_text(
                        f"⚠️ *SYSTEM ALERT — Scanner Silent*\n"
                        f"No heartbeat sent in {int(gap/60)} minutes.\n"
                        f"Check Render logs — scanner may have stopped."
                    )
        except Exception:
            pass

        time.sleep(3600)  # 1 hour

# Start background thread
_scanner_thread = threading.Thread(target=_hourly_scheduler, daemon=True)
_scanner_thread.start()

# ── Frontend ──────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory(FRONTEND, 'index.html')

@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory(FRONTEND, filename)

# ── Market ────────────────────────────────────────────────────────────────────
@app.route('/api/market/overview')
def market_overview():
    prices = get_current_prices()
    fg = get_fear_greed_index()
    sectors = {}
    for sym, info in prices.items():
        s = info.get('sector','Other')
        sectors.setdefault(s,[]).append(info.get('change_24h',0))
    return jsonify({
        'prices': prices, 'fear_greed': fg,
        'sector_performance': {s: round(float(np.mean(v)),2) for s,v in sectors.items()},
        'coins': list(COINS.keys()),
    })

@app.route('/api/coin/<symbol>')
def coin_analysis(symbol):
    symbol = symbol.upper()
    if symbol not in COINS:
        return jsonify({'error': f'Unknown symbol: {symbol}'}), 404
    prices = get_current_prices()
    df     = generate_ohlcv(symbol, 300)
    ta     = analyze(symbol, df)
    sent   = get_sentiment_score(symbol)
    oc     = get_onchain_metrics(symbol)
    sig    = generate_signal(symbol, ta['current_price'], ta['indicators'],
                             ta['patterns'], sent, oc,
                             ta['support_levels'], ta['resistance_levels'],
                             ta['market_regime'], prices[symbol].get('change_24h',0))
    return jsonify({
        'symbol': symbol, 'name': COINS[symbol]['name'],
        'sector': COINS[symbol]['sector'],
        'price_info': prices[symbol],
        'technical_analysis': ta, 'sentiment': sent, 'onchain': oc,
        'signal': asdict(sig),
        'timestamp': __import__('datetime').datetime.now().isoformat(),
    })

@app.route('/api/signals/top')
def top_signals():
    coins  = ['BTC','ETH','XRP','XLM','HBAR','SOL','BNB','AVAX','LINK','ARB','SUI','INJ','CHZ','PSG','BAR']
    prices = get_current_prices()
    results = []
    for sym in coins:
        df   = generate_ohlcv(sym, 300)
        ta   = analyze(sym, df)
        sent = get_sentiment_score(sym)
        oc   = get_onchain_metrics(sym)
        sig  = generate_signal(sym, ta['current_price'], ta['indicators'],
                               ta['patterns'], sent, oc,
                               ta['support_levels'], ta['resistance_levels'],
                               ta['market_regime'], prices[sym].get('change_24h',0))
        results.append({'symbol':sym,'name':COINS[sym]['name'],
                        'signal':asdict(sig),'technical_analysis':ta,'price_info':prices[sym]})
    ranked = sorted(results, key=lambda x: x['signal']['confidence'], reverse=True)
    return jsonify({
        'buy_signals':  [r for r in ranked if r['signal']['action']=='BUY'][:4],
        'sell_signals': [r for r in ranked if r['signal']['action']=='SELL'][:2],
        'hold_signals': [r for r in ranked if r['signal']['action']=='HOLD'][:2],
        'coins_scanned': len(coins),
    })

@app.route('/api/market/heatmap')
def heatmap():
    prices = get_current_prices()
    return jsonify([{'symbol':s,'name':i['name'],'price':i['price'],
                     'change_24h':i['change_24h'],'sector':i['sector']}
                    for s,i in prices.items()])

@app.route('/api/strategy/competition')
def strategy_competition():
    return jsonify(generate_competition_data(28))

# ── Notifications ─────────────────────────────────────────────────────────────
@app.route('/api/notifications/status')
def notifications_status():
    return jsonify({
        'telegram_configured': _tg_configured(),
        'sms_configured':      _sms_configured(),
        'any_configured':      _is_configured(),
        'primary':             'telegram' if _tg_configured() else ('sms' if _sms_configured() else 'none'),
        'threshold':           7.5,
        'hourly_scan':         'active',
        'last_scan':           _last_scan_result.get('last_run'),
    })

@app.route('/api/notifications/test', methods=['POST'])
def test_notification():
    test_signal = {
        'symbol':'XRP','action':'BUY','confidence':8.5,
        'entry_price':1.38,'target_1':1.52,'stop_loss':1.28,'risk_reward':2.1,
        'signal_strength':'STRONG',
        'top_reasons':[
            'RSI oversold at 28 — historically strong buy zone',
            'MACD bullish crossover — momentum just shifted upward',
            'Exchange outflows — investors moving coins off exchanges',
        ]
    }
    if _tg_configured():
        result = send_telegram(test_signal)
    elif _sms_configured():
        result = send_sms(test_signal)
    else:
        result = {'sent':False,'message':'No notification method configured.'}
    return jsonify(result)

@app.route('/api/notifications/scan', methods=['POST'])
def scan_and_alert():
    _run_scan()
    return jsonify(_last_scan_result)

@app.route('/api/notifications/last_scan')
def last_scan():
    return jsonify(_last_scan_result)


# ── Telegram webhook — fires when someone joins the group ─────────────────────
@app.route('/api/telegram/webhook', methods=['POST'])
def telegram_webhook():
    """
    Telegram sends a POST here for every group event.
    We listen for new_chat_members and send the welcome message.
    Register this webhook URL in Telegram once after deploy.
    """
    try:
        data = request.get_json(silent=True) or {}
        message = data.get('message', {})
        new_members = message.get('new_chat_members', [])
        if new_members:
            for member in new_members:
                # Skip if the new member is the bot itself
                if member.get('is_bot'):
                    continue
                first_name = member.get('first_name', '')
                username   = member.get('username', '')
                name = f"@{username}" if username else first_name
                send_welcome(name)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/api/notifications/welcome', methods=['POST'])
def send_welcome_manual():
    """Manually trigger the welcome message — useful for testing."""
    result = send_welcome()
    return jsonify(result)

@app.route('/api/telegram/set_webhook', methods=['POST'])
def set_webhook():
    """
    Register the webhook URL with Telegram so it knows where to send updates.
    Call this once after deploying by hitting this endpoint.
    """
    import urllib.request, json as _json
    try:
        from notifications import _tg_config
        cfg = _tg_config()
        if not cfg['token']:
            return jsonify({'ok': False, 'message': 'No token configured'})
        # Build the webhook URL from the request
        host = request.host_url.rstrip('/')
        webhook_url = f"{host}/api/telegram/webhook"
        url = f"https://api.telegram.org/bot{cfg['token']}/setWebhook"
        payload = _json.dumps({"url": webhook_url}).encode()
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            result = _json.loads(resp.read())
        return jsonify({**result, 'webhook_url': webhook_url})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


# ── Kalshi Prediction Markets ────────────────────────────────────────────────
@app.route('/api/kalshi/markets')
def kalshi_markets():
    return jsonify(get_kalshi_markets())

@app.route('/api/kalshi/scan', methods=['POST'])
def kalshi_scan():
    import datetime as _dt
    data = get_kalshi_markets(force_refresh=True)
    if _tg_configured():
        recs = data.get('recommended', [])
        now_str = _dt.datetime.now().strftime('%H:%M UTC')
        if recs:
            msg = f"🎲 *Kalshi Scan — {now_str}*\n"
            msg += f"Found {len(recs)} high-edge markets\n\n"
            for m in recs[:4]:
                edge_pct = round(m['best_edge'] * 100, 1)
                msg += (f"{'🟢' if m['best_side']=='YES' else '🔴'} "
                        f"*{m['best_side']}* — {edge_pct}% edge\n"
                        f"_{m['title'][:60]}_\n"
                        f"Price: {m['best_price']:.2f} · Odds: {m['odds']}x · "
                        f"Bet: ${m['bet_size']}\n\n")
            send_telegram_text(msg)
        else:
            send_telegram_text(f"🎲 *Kalshi Scan — {now_str}*\nScanned {data['scanned']} markets — no edges above threshold.")
    return jsonify(data)



# ── System Status & Safety ────────────────────────────────────────────────────
@app.route('/api/system/status')
def system_status():
    """Returns full system health including circuit breaker and funding rates."""
    import datetime as _dt
    heartbeat_age = None
    if _last_heartbeat_sent:
        heartbeat_age = int((_dt.datetime.now() - _last_heartbeat_sent).total_seconds())
    return jsonify({
        "circuit_breaker_active": _execution_halted,
        "halt_reason":            _halt_reason,
        "last_heartbeat_sent":    _last_heartbeat_sent.isoformat() if _last_heartbeat_sent else None,
        "heartbeat_age_seconds":  heartbeat_age,
        "heartbeat_ok":           heartbeat_age is None or heartbeat_age < 5400,
        "last_scan":              _last_scan_result.get("last_run"),
        "funding_rates":          get_all_rates(),
        "funding_summary":        funding_summary(),
    })

@app.route('/api/system/circuit-breaker/reset', methods=['POST'])
def reset_circuit_breaker():
    """Manually reset the circuit breaker via API."""
    global _execution_halted, _halt_reason
    _execution_halted = False
    _halt_reason = ""
    return jsonify({"ok": True, "message": "Circuit breaker reset. Execution resumed."})

@app.route('/api/market/regime-overview')
def regime_overview():
    """Returns the current market regime for all scanned coins."""
    coins = ['BTC','ETH','XRP','XLM','HBAR','SOL','BNB','AVAX','LINK','ARB','SUI','INJ']
    results = []
    for sym in coins:
        try:
            df  = generate_ohlcv(sym, 100)
            ta  = analyze(sym, df)
            results.append({
                "symbol":  sym,
                "tier":    get_coin_tier(sym),
                "regime":  ta['market_regime'],
                "adx":     ta.get('adx_value', 0),
                "bb_bw":   ta['indicators'].get('bb_bandwidth', 0),
                "bb_bw_avg": ta['indicators'].get('bb_bw_avg_30', 0),
                "price":   ta['current_price'],
            })
        except Exception:
            pass
    return jsonify({"regimes": results, "timestamp": __import__('datetime').datetime.now().isoformat()})

# ── Trump Tracker API ────────────────────────────────────────────────────────
@app.route('/api/trump/posts')
def trump_posts():
    limit = int(request.args.get('limit', 20))
    posts = get_trump_posts(limit=limit)
    stats = get_trump_stats()
    return jsonify({"posts": posts, "stats": stats,
                    "generated_at": __import__('datetime').datetime.now().isoformat()})

@app.route('/api/trump/scan', methods=['POST'])
def trump_scan_now():
    try:
        init_trump_db()
        alerts = run_trump_scan(
            send_telegram_fn=send_telegram_text if _tg_configured() else None,
            tg_configured_fn=_tg_configured)
        return jsonify({"ok": True, "new_alerts": len(alerts),
                        "posts": get_trump_posts(10), "stats": get_trump_stats()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

# ── Catalyst Calendar API ────────────────────────────────────────────────────
@app.route('/api/catalyst/upcoming')
def catalyst_upcoming():
    days = int(request.args.get('days', 90))
    catalysts = get_upcoming_catalysts(days_ahead=days)
    coin_catalysts = get_catalyst_coins()
    return jsonify({"catalysts": catalysts, "coin_catalysts": coin_catalysts,
                    "total": len(catalysts), "generated_at": __import__('datetime').datetime.now().isoformat()})

# ── Signal Log API ────────────────────────────────────────────────────────────
@app.route('/api/signal-log/signals')
def api_signal_log():
    symbol  = request.args.get('symbol')
    outcome = request.args.get('outcome')
    limit   = int(request.args.get('limit', 200))
    return jsonify(get_signals(limit=limit, symbol=symbol, outcome=outcome))

@app.route('/api/signal-log/kalshi')
def api_kalshi_log():
    return jsonify(get_kalshi_signals(limit=100))

@app.route('/api/signal-log/stats')
def api_signal_stats():
    return jsonify(get_stats())

@app.route('/api/signal-log/outcome', methods=['POST'])
def api_update_outcome():
    """
    Update the outcome of a logged signal.
    Body: { id, outcome, exit_price (optional), notes (optional) }
    """
    data = request.get_json(silent=True) or {}
    sig_id = data.get('id')
    outcome = data.get('outcome')
    if not sig_id or not outcome:
        return jsonify({'ok': False, 'error': 'id and outcome required'}), 400
    valid_outcomes = {'PENDING','WIN_TP1','WIN_TP2','LOSS','EXPIRED'}
    if outcome not in valid_outcomes:
        return jsonify({'ok': False, 'error': f'outcome must be one of {valid_outcomes}'}), 400
    update_outcome(sig_id, outcome, data.get('exit_price'), data.get('notes'))
    return jsonify({'ok': True})

@app.route('/api/signal-log/kalshi-outcome', methods=['POST'])
def api_update_kalshi_outcome():
    data = request.get_json(silent=True) or {}
    kid = data.get('id')
    outcome = data.get('outcome')
    if not kid or not outcome:
        return jsonify({'ok': False, 'error': 'id and outcome required'}), 400
    update_kalshi_outcome(kid, outcome, data.get('pnl'), data.get('notes'))
    return jsonify({'ok': True})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
