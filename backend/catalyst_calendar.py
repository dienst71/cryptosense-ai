"""CryptoSense AI — Catalyst Calendar Q2 2026"""
from datetime import datetime, date

CATALYSTS = [
    {"id":"clarity_act","date":"2026-04-03","title":"CLARITY Act Signing","description":"Trump signs CLARITY Act — splits crypto regulation between SEC and CFTC. Removes primary legal uncertainty blocking institutional investors.","impact":"HIGH","direction":"BULLISH","coins":["XRP","SOL","AVAX","ADA","DOGE","LINK"],"notes":"XRP, SOL, ADA, AVAX most impacted. Ripple CEO gives 80-90% passage odds.","source":"Multiple analysts, JPMorgan"},
    {"id":"uk_crypto_isa","date":"2026-04-06","title":"UK Crypto ETNs in ISAs/Pensions","description":"UK allows crypto ETNs inside tax-advantaged ISAs and pensions.","impact":"MEDIUM","direction":"BULLISH","coins":["BTC","ETH"],"notes":"Primarily benefits BTC and ETH as first assets UK pension funds will target.","source":"UK FCA"},
    {"id":"clarity_senate","date":"2026-04-15","title":"CLARITY Act Senate Committee","description":"Senate Banking Committee markup. Passage signals bill reaches full Senate vote.","impact":"HIGH","direction":"BULLISH","coins":["XRP","SOL","AVAX","ADA","LINK"],"notes":"Senator Lummis confirms markup targeted for second half of April.","source":"Senator Lummis office"},
    {"id":"fomc_apr","date":"2026-04-29","title":"FOMC Meeting (Powell Last)","description":"Federal Reserve rate decision. Likely Powell final meeting as Fed Chair.","impact":"HIGH","direction":"VOLATILE","coins":["BTC","ETH"],"notes":"BTC has sold off after 8 of last 9 FOMC meetings. Expect volatility both directions.","source":"Federal Reserve"},
    {"id":"warsh_transition","date":"2026-05-15","title":"New Fed Chair Kevin Warsh","description":"Warsh replaces Powell. Expected to push for rate cuts. Called Bitcoin the new gold.","impact":"HIGH","direction":"BULLISH","coins":["BTC","ETH","SOL"],"notes":"If Warsh signals rate cuts in early remarks, crypto reaction could be fast and aggressive.","source":"White House, JPMorgan"},
    {"id":"world_cup","date":"2026-06-11","title":"FIFA World Cup 2026 Opens","description":"World Cup hosted across USA Mexico Canada. SEC/CFTC classified fan tokens as digital collectibles.","impact":"HIGH","direction":"BULLISH","coins":["CHZ","PSG","BAR"],"notes":"CHZ up 30pct in last 30 days on whale accumulation. Buy-the-rumor trade.","source":"FIFA, Chiliz roadmap"},
    {"id":"eth_glamsterdam","date":"2026-06-15","title":"Ethereum Glamsterdam Upgrade","description":"Ethereum biggest upgrade since The Merge. Improves throughput and validator economics.","impact":"HIGH","direction":"BULLISH","coins":["ETH","LINK"],"notes":"Pre-upgrade positioning opens now. If timeline slips to Q3, reduce position size.","source":"Ethereum Foundation"},
    {"id":"fomc_jun","date":"2026-06-18","title":"FOMC Meeting Warsh First","description":"Kevin Warsh first meeting as Fed Chair. Markets watch closely for rate cut signals.","impact":"HIGH","direction":"BULLISH","coins":["BTC","ETH","SOL"],"notes":"If Warsh signals dovish pivot here, could be biggest macro catalyst for crypto in 2026.","source":"Federal Reserve"},
    {"id":"mica_deadline","date":"2026-07-01","title":"EU MiCA Full Implementation","description":"EU Markets in Crypto-Assets regulation fully in effect across all EU member states.","impact":"MEDIUM","direction":"BULLISH","coins":["BTC","ETH"],"notes":"Reduces regulatory risk premium for European institutional investors.","source":"European Commission"},
]

def get_upcoming_catalysts(days_ahead=90):
    today = date.today()
    upcoming = []
    for c in CATALYSTS:
        event_date = datetime.strptime(c["date"], "%Y-%m-%d").date()
        days_until = (event_date - today).days
        if -7 <= days_until <= days_ahead:
            upcoming.append({**c,"days_until":days_until,"days_label":("TODAY" if days_until==0 else f"{abs(days_until)}d ago" if days_until<0 else f"in {days_until}d"),"is_past":days_until<0,"is_imminent":0<=days_until<=7})
    upcoming.sort(key=lambda x: x["date"])
    return upcoming

def get_catalyst_coins():
    coin_catalysts = {}
    for c in CATALYSTS:
        event_date = datetime.strptime(c["date"], "%Y-%m-%d").date()
        days_until = (event_date - date.today()).days
        if days_until < -7: continue
        for coin in c["coins"]:
            if coin not in coin_catalysts: coin_catalysts[coin] = []
            coin_catalysts[coin].append({"title":c["title"],"date":c["date"],"days_until":days_until,"impact":c["impact"],"direction":c["direction"]})
    return coin_catalysts
# v24 catalyst calendar
