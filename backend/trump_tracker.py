
import urllib.request, json, sqlite3, time, datetime, os, re, hashlib
DB_PATH = os.environ.get("SIGNAL_LOG_PATH", "/tmp/signal_log.db").replace("signal_log.db", "trump_tracker.db")
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MARKET_KEYWORDS = ["tariff","sanction","great time to buy","rate cut","fed","bitcoin","crypto","stock market","trade deal","billion","trillion","nvidia","apple","tesla","energy","oil","gold","china","tax","deal","investment","company","ceo","executive order","buy","market","interest rate","economy","inflation","jobs","bank","dollar"]
SCORE_PROMPT = """You are a financial market analyst. Analyze this Trump post and return ONLY valid JSON with no markdown:
Post: {post_text}
Source: {source}
Date: {date}
Return: {{"impact_level":"CRITICAL|HIGH|MEDIUM|LOW","market_direction":"BULLISH|BEARISH|VOLATILE|NEUTRAL","affected_assets":{{"crypto":[],"stocks":[],"sectors":[],"commodities":[]}},"trade_recommendation":"one sentence or empty","reasoning":"one sentence","keywords":[],"time_sensitivity":"IMMEDIATE|HOURS|DAYS|NONE"}}
CRITICAL=tariff/buy signal/rate cut/company attack. HIGH=policy/crypto mention/trade deal. MEDIUM=economic commentary. LOW=no market relevance. Only use crypto: BTC ETH SOL XRP BNB AVAX LINK ADA DOGE"""

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS trump_posts (id INTEGER PRIMARY KEY AUTOINCREMENT, post_hash TEXT UNIQUE, detected_at TEXT, post_date TEXT, post_text TEXT, source TEXT, impact_level TEXT, market_direction TEXT, affected_crypto TEXT, affected_stocks TEXT, affected_sectors TEXT, trade_recommendation TEXT, reasoning TEXT, keywords TEXT, time_sensitivity TEXT, alert_sent INTEGER DEFAULT 0)""")
    conn.commit(); conn.close()

def _hash(text): return hashlib.md5(text.strip().lower()[:200].encode()).hexdigest()

def _already_seen(h):
    try:
        conn = sqlite3.connect(DB_PATH)
        r = conn.execute("SELECT id FROM trump_posts WHERE post_hash=?", (h,)).fetchone()
        conn.close(); return r is not None
    except: return False

def _save_post(post_hash, post_text, source, scoring, post_date=""):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT OR IGNORE INTO trump_posts (post_hash,detected_at,post_date,post_text,source,impact_level,market_direction,affected_crypto,affected_stocks,affected_sectors,trade_recommendation,reasoning,keywords,time_sensitivity) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (post_hash, datetime.datetime.now().isoformat(), post_date, post_text[:1000], source, scoring.get("impact_level","LOW"), scoring.get("market_direction","NEUTRAL"), json.dumps(scoring.get("affected_assets",{}).get("crypto",[])), json.dumps(scoring.get("affected_assets",{}).get("stocks",[])), json.dumps(scoring.get("affected_assets",{}).get("sectors",[])), scoring.get("trade_recommendation",""), scoring.get("reasoning",""), json.dumps(scoring.get("keywords",[])), scoring.get("time_sensitivity","NONE")))
        conn.commit(); conn.close()
    except: pass

def score_with_claude(post_text, source, date):
    api_key = os.environ.get("ANTHROPIC_API_KEY","")
    if not api_key:
        tl = post_text.lower()
        crypto = next(([c] for k,c in [("bitcoin","BTC"),("btc","BTC"),("ethereum","ETH"),("eth","ETH"),("solana","SOL"),("sol","SOL"),("xrp","XRP"),("crypto","BTC"),("doge","DOGE")] if k in tl), [])
        impact = "HIGH" if any(w in tl for w in ["tariff","sanction","great time to buy","rate cut","trade deal"]) else "MEDIUM" if any(w in tl for w in MARKET_KEYWORDS) else "LOW"
        return {"impact_level":impact,"market_direction":"BULLISH" if any(w in tl for w in ["buy","deal","great","win","cut"]) else "BEARISH" if any(w in tl for w in ["tariff","sanction","ban"]) else "NEUTRAL","affected_assets":{"crypto":crypto,"stocks":[],"sectors":[],"commodities":[]},"trade_recommendation":"","reasoning":"Keyword scoring","keywords":[],"time_sensitivity":"IMMEDIATE" if impact=="HIGH" else "NONE"}
    try:
        payload = json.dumps({"model":"claude-sonnet-4-6","max_tokens":400,"messages":[{"role":"user","content":SCORE_PROMPT.format(post_text=post_text[:500],source=source,date=date)}]}).encode()
        req = urllib.request.Request(ANTHROPIC_API_URL, data=payload, headers={"Content-Type":"application/json","x-api-key":api_key,"anthropic-version":"2023-06-01"}, method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read())
            text = re.sub(r"```json\s*|\s*```","",resp["content"][0]["text"].strip()).strip()
            return json.loads(text)
    except Exception as e:
        return {"impact_level":"LOW","market_direction":"NEUTRAL","affected_assets":{"crypto":[],"stocks":[],"sectors":[],"commodities":[]},"trade_recommendation":"","reasoning":str(e)[:100],"keywords":[],"time_sensitivity":"NONE"}

def fetch_trump_posts():
    posts = []
    try:
        url = "https://html.duckduckgo.com/html/?q=Trump+Truth+Social+statement+tariff+market+today&df=d"
        req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36","Accept":"text/html"})
        with urllib.request.urlopen(req, timeout=12) as r: html = r.read().decode("utf-8",errors="replace")
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</[^>]+>', html, re.DOTALL)
        titles   = re.findall(r'class="result__a"[^>]*>(.*?)</a>', html, re.DOTALL)
        links    = re.findall(r'class="result__url"[^>]*>(.*?)</[^>]+>', html, re.DOTALL)
        for i, snippet in enumerate(snippets[:10]):
            clean = re.sub(r"\s+"," ",re.sub(r"<[^>]+>","",snippet)).strip()
            if len(clean)<50: continue
            title = re.sub(r"<[^>]+>","",titles[i]).strip() if i<len(titles) else ""
            source = links[i].strip() if i<len(links) else "news"
            posts.append({"text":(f"{title} — {clean}" if title else clean)[:600],"source":source[:100],"date":datetime.datetime.now().strftime("%Y-%m-%d")})
    except: pass
    return posts

def format_trump_alert(post_text, scoring, source):
    impact=scoring.get("impact_level","LOW"); direction=scoring.get("market_direction","NEUTRAL")
    assets=scoring.get("affected_assets",{}); rec=scoring.get("trade_recommendation",""); reasoning=scoring.get("reasoning","")
    sensitivity=scoring.get("time_sensitivity","NONE")
    ie={"CRITICAL":"🚨","HIGH":"⚠️","MEDIUM":"📢","LOW":"ℹ️"}.get(impact,"📢")
    de={"BULLISH":"🟢","BEARISH":"🔴","VOLATILE":"⚡","NEUTRAL":"🟡"}.get(direction,"🟡")
    tt=" — ACT NOW" if sensitivity=="IMMEDIATE" else " — Next Few Hours" if sensitivity=="HOURS" else ""
    crypto=", ".join(assets.get("crypto",[])); stocks=", ".join(assets.get("stocks",[])); sectors=", ".join(assets.get("sectors",[]))
    msg=f"{ie} *TRUMP SIGNAL — {impact}{tt}*\n━━━━━━━━━━━━━━━━━━━━━\n{de} *{direction}*\n\n_{post_text[:300]}_\n\n"
    if crypto: msg+=f"🪙 *Crypto:* {crypto}\n"
    if stocks: msg+=f"📈 *Stocks:* {stocks}\n"
    if sectors: msg+=f"🏭 *Sectors:* {sectors}\n"
    if reasoning: msg+=f"\n💡 _{reasoning}_\n"
    if rec: msg+=f"\n🎯 *Trade idea:* {rec}\n"
    msg+=f"\n_Detected: {datetime.datetime.now().strftime('%H:%M UTC')}_"
    return msg

def get_recent_posts(limit=20):
    try:
        conn=sqlite3.connect(DB_PATH)
        rows=conn.execute("SELECT detected_at,post_date,post_text,source,impact_level,market_direction,affected_crypto,affected_stocks,affected_sectors,trade_recommendation,reasoning,time_sensitivity,alert_sent FROM trump_posts ORDER BY detected_at DESC LIMIT ?",(limit,)).fetchall()
        conn.close()
        return [{"detected_at":r[0],"post_date":r[1],"post_text":r[2],"source":r[3],"impact_level":r[4],"market_direction":r[5],"affected_crypto":json.loads(r[6] or "[]"),"affected_stocks":json.loads(r[7] or "[]"),"affected_sectors":json.loads(r[8] or "[]"),"trade_recommendation":r[9],"reasoning":r[10],"time_sensitivity":r[11],"alert_sent":r[12]} for r in rows]
    except: return []

def get_stats():
    try:
        conn=sqlite3.connect(DB_PATH)
        total=conn.execute("SELECT COUNT(*) FROM trump_posts").fetchone()[0]
        critical=conn.execute("SELECT COUNT(*) FROM trump_posts WHERE impact_level='CRITICAL'").fetchone()[0]
        high=conn.execute("SELECT COUNT(*) FROM trump_posts WHERE impact_level='HIGH'").fetchone()[0]
        alerts=conn.execute("SELECT COUNT(*) FROM trump_posts WHERE alert_sent=1").fetchone()[0]
        conn.close(); return {"total":total,"critical":critical,"high":high,"alerts_sent":alerts}
    except: return {"total":0,"critical":0,"high":0,"alerts_sent":0}

def run_trump_scan(send_telegram_fn=None, tg_configured_fn=None):
    init_db(); new_alerts=[]
    for post in fetch_trump_posts():
        h=_hash(post["text"])
        if _already_seen(h): continue
        if not any(kw in post["text"].lower() for kw in MARKET_KEYWORDS): continue
        scoring=score_with_claude(post["text"],post["source"],post["date"])
        _save_post(h,post["text"],post["source"],scoring,post["date"])
        if scoring.get("impact_level","LOW") in ("CRITICAL","HIGH"):
            new_alerts.append({"post":post,"scoring":scoring})
            if send_telegram_fn and tg_configured_fn and tg_configured_fn():
                try:
                    send_telegram_fn(format_trump_alert(post["text"],scoring,post["source"]))
                    conn=sqlite3.connect(DB_PATH); conn.execute("UPDATE trump_posts SET alert_sent=1 WHERE post_hash=?",(h,)); conn.commit(); conn.close()
                except: pass
    return new_alerts
