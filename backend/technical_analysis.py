"""CryptoSense AI — Technical Analysis Engine"""
import numpy as np
import pandas as pd

def sma(s, n): return s.rolling(n).mean()
def ema(s, n): return s.ewm(span=n, adjust=False).mean()

def rsi(s, n=14):
    d = s.diff()
    g = d.clip(lower=0).ewm(com=n-1, min_periods=n).mean()
    l = (-d.clip(upper=0)).ewm(com=n-1, min_periods=n).mean()
    return 100 - 100/(1 + g/l.replace(0, np.nan))

def macd(s, fast=12, slow=26, sig=9):
    m = ema(s,fast) - ema(s,slow)
    signal = ema(m, sig)
    return m, signal, m - signal

def bollinger(s, n=20, k=2.0):
    mid = sma(s, n); std = s.rolling(n).std()
    up = mid + k*std; lo = mid - k*std
    return up, mid, lo, (s-lo)/(up-lo), (up-lo)/mid

def atr(df, n=14):
    h,l,c = df["high"],df["low"],df["close"]
    tr = pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    return tr.ewm(com=n-1, min_periods=n).mean()

def obv(df):
    return (np.sign(df["close"].diff())*df["volume"]).fillna(0).cumsum()

def vwap(df):
    tp = (df["high"]+df["low"]+df["close"])/3
    return (tp*df["volume"]).cumsum()/df["volume"].cumsum()

def stochastic(df, k=14, d=3):
    lo = df["low"].rolling(k).min(); hi = df["high"].rolling(k).max()
    K = 100*(df["close"]-lo)/(hi-lo).replace(0,np.nan)
    return K, sma(K,d)

def mfi(df, n=14):
    tp = (df["high"]+df["low"]+df["close"])/3
    mf = tp*df["volume"]
    pos = mf.where(tp>tp.shift(),0); neg = mf.where(tp<tp.shift(),0)
    return 100 - 100/(1 + pos.rolling(n).sum()/neg.rolling(n).sum().replace(0,np.nan))

def adx(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    up   = h - h.shift(1)
    down = l.shift(1) - l
    plus_dm  = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)
    tr_s  = atr(df, n)
    plus_di  = 100 * ema(plus_dm, n) / tr_s.replace(0, np.nan)
    minus_di = 100 * ema(minus_dm, n) / tr_s.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return ema(dx, n)

def parabolic_sar(df, af0=0.02, af_step=0.02, af_max=0.2):
    c,h,l = df["close"].values, df["high"].values, df["low"].values
    n = len(c); sar = np.zeros(n); ep = np.zeros(n); af = af0; bull = True
    sar[0]=l[0]; ep[0]=h[0]
    for i in range(1,n):
        sar[i] = sar[i-1]+af*(ep[i-1]-sar[i-1])
        if bull:
            sar[i] = min(sar[i], l[i-1], l[i-2] if i>1 else l[i-1])
            if l[i]<sar[i]: bull=False; sar[i]=ep[i-1]; ep[i]=l[i]; af=af0
            else:
                if h[i]>ep[i-1]: ep[i]=h[i]; af=min(af+af_step,af_max)
                else: ep[i]=ep[i-1]
        else:
            sar[i] = max(sar[i], h[i-1], h[i-2] if i>1 else h[i-1])
            if h[i]>sar[i]: bull=True; sar[i]=ep[i-1]; ep[i]=h[i]; af=af0
            else:
                if l[i]<ep[i-1]: ep[i]=l[i]; af=min(af+af_step,af_max)
                else: ep[i]=ep[i-1]
    return pd.Series(sar, index=df.index)

def detect_patterns(df):
    if len(df)<3: return []
    c=df.iloc[-1]; p1=df.iloc[-2]; p2=df.iloc[-3]
    body=abs(c["close"]-c["open"]); rng=c["high"]-c["low"]
    uw=c["high"]-max(c["close"],c["open"]); lw=min(c["close"],c["open"])-c["low"]
    pats=[]
    if rng>0 and body/rng<0.1: pats.append(("Doji","neutral",0.55))
    if lw>body*2 and uw<body*0.5: pats.append(("Hammer","bullish",0.70))
    if uw>body*2 and lw<body*0.5 and c["close"]<c["open"]: pats.append(("Shooting Star","bearish",0.68))
    if (p1["close"]<p1["open"] and c["close"]>c["open"] and
        c["open"]<p1["close"] and c["close"]>p1["open"]):
        pats.append(("Bullish Engulfing","bullish",0.78))
    if (p1["close"]>p1["open"] and c["close"]<c["open"] and
        c["open"]>p1["close"] and c["close"]<p1["open"]):
        pats.append(("Bearish Engulfing","bearish",0.78))
    return pats

def find_sr(df, window=20):
    h,l = df["high"],df["low"]; res=[]; sup=[]
    for i in range(window, len(df)-window):
        if h.iloc[i]==h.iloc[i-window:i+window].max(): res.append(h.iloc[i])
        if l.iloc[i]==l.iloc[i-window:i+window].min(): sup.append(l.iloc[i])
    def cluster(lvls, tol=0.015):
        if not lvls: return []
        lvls=sorted(lvls); cl=[[lvls[0]]]
        for v in lvls[1:]:
            if (v-cl[-1][-1])/cl[-1][-1]<tol: cl[-1].append(v)
            else: cl.append([v])
        return [np.mean(c) for c in cl]
    return cluster(sup)[-3:], cluster(res)[:3]

def analyze(symbol, df):
    cl = df["close"]; price = cl.iloc[-1]
    e9=ema(cl,9); e21=ema(cl,21); e50=ema(cl,50)
    e200=ema(cl,200) if len(cl)>=200 else ema(cl,50)
    r14=rsi(cl); ml,ms,mh=macd(cl)
    bb_up,bb_mid,bb_lo,bb_pct,bb_bw=bollinger(cl)
    atr14=atr(df); sar=parabolic_sar(df)
    obv_s=obv(df); vwap_s=vwap(df); mfi14=mfi(df)
    stk,std=stochastic(df)
    adx14=adx(df)
    ema_cross = ("Golden Cross" if e9.iloc[-1]>e21.iloc[-1] and e9.iloc[-2]<=e21.iloc[-2]
                 else "Death Cross" if e9.iloc[-1]<e21.iloc[-1] and e9.iloc[-2]>=e21.iloc[-2]
                 else "Above 21 EMA" if e9.iloc[-1]>e21.iloc[-1] else "Below 21 EMA")
    macd_bias = ("Bullish Crossover" if mh.iloc[-1]>0 and mh.iloc[-2]<=0
                 else "Bearish Crossover" if mh.iloc[-1]<0 and mh.iloc[-2]>=0
                 else "Bullish" if mh.iloc[-1]>0 else "Bearish")
    sup, res = find_sr(df)
    adx_val = float(adx14.iloc[-1]) if not np.isnan(adx14.iloc[-1]) else 15.0
    bb_bw_now = float(bb_bw.iloc[-1])
    bb_bw_avg = float(bb_bw.rolling(30).mean().iloc[-1]) if len(bb_bw) >= 30 else bb_bw_now
    bb_expanding = bb_bw_now > bb_bw_avg * 1.2
    trending_up   = price > e50.iloc[-1] and e50.iloc[-1] > e200.iloc[-1]
    trending_down = price < e50.iloc[-1] and e50.iloc[-1] < e200.iloc[-1]
    atr_pct = float(atr14.iloc[-1]) / price
    if adx_val >= 25 and trending_up:       regime = "Trending Bull"
    elif adx_val >= 25 and trending_down:   regime = "Trending Bear"
    elif adx_val < 20 and not bb_expanding: regime = "Ranging / Consolidating"
    elif atr_pct > 0.06 or bb_expanding:   regime = "High Volatility"
    else:                                   regime = "Transitional"
    return {
        "symbol": symbol, "current_price": round(price, 8),
        "indicators": {
            "rsi_14": round(float(r14.iloc[-1]), 2),
            "macd_line": round(float(ml.iloc[-1]), 6),
            "macd_signal": round(float(ms.iloc[-1]), 6),
            "macd_histogram": round(float(mh.iloc[-1]), 6),
            "macd_bias": macd_bias,
            "bb_upper": round(float(bb_up.iloc[-1]), 8),
            "bb_lower": round(float(bb_lo.iloc[-1]), 8),
            "bb_position": round(float(bb_pct.iloc[-1]), 4),
            "bb_bandwidth": round(bb_bw_now, 4),
            "bb_bw_avg_30": round(bb_bw_avg, 4),
            "adx_14": round(adx_val, 2),
            "adx_trend": "Strong" if adx_val >= 25 else "Weak" if adx_val < 20 else "Moderate",
            "atr_14": round(float(atr14.iloc[-1]), 8),
            "ema_9": round(float(e9.iloc[-1]), 8),
            "ema_21": round(float(e21.iloc[-1]), 8),
            "ema_50": round(float(e50.iloc[-1]), 8),
            "ema_200": round(float(e200.iloc[-1]), 8),
            "ema_cross": ema_cross,
            "stoch_k": round(float(stk.iloc[-1]), 2),
            "stoch_d": round(float(std.iloc[-1]), 2),
            "obv_trend": "Rising" if obv_s.iloc[-1]>obv_s.iloc[-10] else "Falling",
            "mfi_14": round(float(mfi14.iloc[-1]), 2),
            "vwap": round(float(vwap_s.iloc[-1]), 8),
            "parabolic_sar": round(float(sar.iloc[-1]), 8),
            "sar_signal": "Bullish" if price>sar.iloc[-1] else "Bearish",
        },
        "patterns": [{"name":p[0],"direction":p[1],"confidence":p[2]} for p in detect_patterns(df)],
        "support_levels": [round(s,8) for s in sup],
        "resistance_levels": [round(r,8) for r in res],
        "market_regime": regime,
        "adx_value": round(adx_val, 2),
        "price_series": cl.tail(100).round(8).tolist(),
        "timestamps": [str(t) for t in cl.tail(100).index],
    }
