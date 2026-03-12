"""
CryptoSense AI — Signal Log
Persistent SQLite database that records every high-confidence signal.
This is your Phase 1 validation infrastructure — track outcomes manually
to build the live performance dataset needed before automated execution.
"""
import sqlite3, os, datetime

# DB path — controlled by SIGNAL_LOG_PATH environment variable
# Free tier default: /tmp/signal_log.db  (resets on deploy — fine for testing)
# Persistent tier: set SIGNAL_LOG_PATH=/data/signal_log.db + add Render Disk at /data
# To upgrade: Render dashboard → your service → Disks → Add Disk → Mount Path: /data
DB_PATH = os.environ.get("SIGNAL_LOG_PATH", "/tmp/signal_log.db")

# ── Schema ────────────────────────────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fired_at    TEXT    NOT NULL,           -- ISO timestamp when signal fired
    symbol      TEXT    NOT NULL,           -- e.g. BTC, ETH
    action      TEXT    NOT NULL,           -- BUY / SELL / HOLD
    confidence  REAL    NOT NULL,           -- 0-10
    model_name  TEXT    NOT NULL,           -- Momentum / Mean Reversion / Breakout / Multi-Factor
    model_id    TEXT    NOT NULL,           -- 1 / 2 / 3 / 4
    price       REAL    NOT NULL,           -- price at time of alert
    entry_price REAL,                       -- same as price, kept for clarity
    target_1    REAL,                       -- TP1
    target_2    REAL,                       -- TP2
    stop_loss   REAL,                       -- stop loss price
    risk_reward REAL,                       -- R:R ratio
    reasons     TEXT,                       -- pipe-separated top reasons
    outcome     TEXT    DEFAULT 'PENDING',  -- PENDING / WIN_TP1 / WIN_TP2 / LOSS / EXPIRED
    exit_price  REAL,                       -- price when closed
    exit_at     TEXT,                       -- ISO timestamp when closed
    pnl_pct     REAL,                       -- P&L in % terms
    notes       TEXT                        -- manual notes field
);

CREATE TABLE IF NOT EXISTS kalshi_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fired_at    TEXT    NOT NULL,
    title       TEXT    NOT NULL,
    category    TEXT,
    side        TEXT,                       -- YES / NO
    price_cents INTEGER,
    fair_value  REAL,
    edge_pct    REAL,
    bet_size    REAL,
    outcome     TEXT    DEFAULT 'PENDING',  -- PENDING / WIN / LOSS / EXPIRED
    payout      REAL,
    pnl         REAL,
    resolved_at TEXT,
    notes       TEXT
);
"""

def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Create tables if they don't exist."""
    with _conn() as c:
        c.executescript(SCHEMA)

# ── Write ─────────────────────────────────────────────────────────────────────
def log_signal(signal: dict) -> int:
    """
    Insert a fired signal into the database.
    Returns the new row ID.
    """
    init_db()
    reasons = " | ".join(signal.get("top_reasons", []))
    now = datetime.datetime.utcnow().isoformat()
    price = signal.get("entry_price") or signal.get("current_price") or 0

    with _conn() as c:
        cur = c.execute("""
            INSERT INTO signals
              (fired_at, symbol, action, confidence, model_name, model_id,
               price, entry_price, target_1, target_2, stop_loss, risk_reward, reasons)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            now,
            signal.get("symbol",""),
            signal.get("action",""),
            signal.get("confidence", 0),
            signal.get("model_name", "Multi-Factor"),
            signal.get("model_id", "4"),
            price, price,
            signal.get("target_1"),
            signal.get("target_2"),
            signal.get("stop_loss"),
            signal.get("risk_reward"),
            reasons,
        ))
        return cur.lastrowid

def log_kalshi(market: dict) -> int:
    """Insert a Kalshi PM alert into the kalshi_log table."""
    init_db()
    now = datetime.datetime.utcnow().isoformat()
    with _conn() as c:
        cur = c.execute("""
            INSERT INTO kalshi_log
              (fired_at, title, category, side, price_cents, fair_value, edge_pct, bet_size, payout)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            now,
            market.get("title",""),
            market.get("category",""),
            market.get("best_side","YES"),
            int(market.get("best_price",0) * 100),
            market.get("fair_value", 0),
            round(market.get("best_edge", 0) * 100, 2),
            market.get("bet_size", 0),
            market.get("payout", 0),
        ))
        return cur.lastrowid

# ── Update outcome ─────────────────────────────────────────────────────────────
def update_outcome(signal_id: int, outcome: str, exit_price: float = None, notes: str = None):
    """
    Mark a signal's outcome. Call this from the dashboard or API.
    outcome: PENDING | WIN_TP1 | WIN_TP2 | LOSS | EXPIRED
    """
    init_db()
    now = datetime.datetime.utcnow().isoformat()

    # Compute P&L % if we have prices
    with _conn() as c:
        row = c.execute("SELECT action, entry_price FROM signals WHERE id=?", (signal_id,)).fetchone()
        pnl = None
        if row and exit_price and row["entry_price"]:
            direction = 1 if row["action"] == "BUY" else -1
            pnl = round(((exit_price - row["entry_price"]) / row["entry_price"]) * 100 * direction, 2)

        c.execute("""
            UPDATE signals
            SET outcome=?, exit_price=?, exit_at=?, pnl_pct=?, notes=?
            WHERE id=?
        """, (outcome, exit_price, now if exit_price else None, pnl, notes, signal_id))

def update_kalshi_outcome(kalshi_id: int, outcome: str, pnl: float = None, notes: str = None):
    """Mark a Kalshi bet as WIN / LOSS / EXPIRED."""
    init_db()
    now = datetime.datetime.utcnow().isoformat()
    with _conn() as c:
        c.execute("""
            UPDATE kalshi_log
            SET outcome=?, pnl=?, resolved_at=?, notes=?
            WHERE id=?
        """, (outcome, pnl, now, notes, kalshi_id))

# ── Read ──────────────────────────────────────────────────────────────────────
def get_signals(limit: int = 100, symbol: str = None, outcome: str = None) -> list:
    """Fetch signals with optional filters. Returns list of dicts."""
    init_db()
    query = "SELECT * FROM signals"
    params = []
    filters = []
    if symbol:
        filters.append("symbol = ?"); params.append(symbol.upper())
    if outcome:
        filters.append("outcome = ?"); params.append(outcome)
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY fired_at DESC LIMIT ?"
    params.append(limit)

    with _conn() as c:
        rows = c.execute(query, params).fetchall()
        return [dict(r) for r in rows]

def get_kalshi_signals(limit: int = 50) -> list:
    """Fetch Kalshi PM log."""
    init_db()
    with _conn() as c:
        rows = c.execute("SELECT * FROM kalshi_log ORDER BY fired_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

def get_stats() -> dict:
    """
    Compute live performance stats from logged signals.
    This is the core of Phase 1 validation.
    """
    init_db()
    with _conn() as c:
        total    = c.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        closed   = c.execute("SELECT COUNT(*) FROM signals WHERE outcome != 'PENDING'").fetchone()[0]
        wins     = c.execute("SELECT COUNT(*) FROM signals WHERE outcome IN ('WIN_TP1','WIN_TP2')").fetchone()[0]
        losses   = c.execute("SELECT COUNT(*) FROM signals WHERE outcome = 'LOSS'").fetchone()[0]
        pending  = c.execute("SELECT COUNT(*) FROM signals WHERE outcome = 'PENDING'").fetchone()[0]

        win_rate = round((wins / closed * 100), 1) if closed > 0 else 0

        avg_win  = c.execute("SELECT AVG(pnl_pct) FROM signals WHERE outcome IN ('WIN_TP1','WIN_TP2') AND pnl_pct IS NOT NULL").fetchone()[0]
        avg_loss = c.execute("SELECT AVG(pnl_pct) FROM signals WHERE outcome = 'LOSS' AND pnl_pct IS NOT NULL").fetchone()[0]
        avg_win  = round(avg_win, 2) if avg_win else None
        avg_loss = round(avg_loss, 2) if avg_loss else None

        rr = round(abs(avg_win / avg_loss), 2) if avg_win and avg_loss and avg_loss != 0 else None

        # By model
        model_rows = c.execute("""
            SELECT model_name,
                   COUNT(*) as total,
                   SUM(CASE WHEN outcome IN ('WIN_TP1','WIN_TP2') THEN 1 ELSE 0 END) as wins,
                   SUM(CASE WHEN outcome = 'LOSS' THEN 1 ELSE 0 END) as losses,
                   AVG(CASE WHEN pnl_pct IS NOT NULL THEN pnl_pct END) as avg_pnl
            FROM signals
            WHERE outcome != 'PENDING'
            GROUP BY model_name
        """).fetchall()
        by_model = []
        for r in model_rows:
            closed_m = r["wins"] + r["losses"]
            wr = round(r["wins"] / closed_m * 100, 1) if closed_m > 0 else 0
            by_model.append({
                "model": r["model_name"],
                "total": r["total"],
                "wins": r["wins"],
                "losses": r["losses"],
                "win_rate": wr,
                "avg_pnl": round(r["avg_pnl"], 2) if r["avg_pnl"] else None,
            })

        # By coin
        coin_rows = c.execute("""
            SELECT symbol,
                   COUNT(*) as total,
                   SUM(CASE WHEN outcome IN ('WIN_TP1','WIN_TP2') THEN 1 ELSE 0 END) as wins,
                   AVG(CASE WHEN pnl_pct IS NOT NULL THEN pnl_pct END) as avg_pnl
            FROM signals WHERE outcome != 'PENDING'
            GROUP BY symbol ORDER BY total DESC
        """).fetchall()
        by_coin = [{"symbol": r["symbol"], "total": r["total"], "wins": r["wins"],
                    "win_rate": round(r["wins"]/r["total"]*100,1) if r["total"] else 0,
                    "avg_pnl": round(r["avg_pnl"],2) if r["avg_pnl"] else None} for r in coin_rows]

        # Kalshi stats
        k_total  = c.execute("SELECT COUNT(*) FROM kalshi_log").fetchone()[0]
        k_wins   = c.execute("SELECT COUNT(*) FROM kalshi_log WHERE outcome='WIN'").fetchone()[0]
        k_closed = c.execute("SELECT COUNT(*) FROM kalshi_log WHERE outcome != 'PENDING'").fetchone()[0]
        k_pnl    = c.execute("SELECT SUM(pnl) FROM kalshi_log WHERE pnl IS NOT NULL").fetchone()[0]

        # Phase 1 readiness check
        ready_for_phase2 = (
            closed >= 50 and
            win_rate >= 48 and
            (rr is None or rr >= 1.8)
        )

        return {
            "total_signals":   total,
            "closed":          closed,
            "pending":         pending,
            "wins":            wins,
            "losses":          losses,
            "win_rate":        win_rate,
            "avg_win_pct":     avg_win,
            "avg_loss_pct":    avg_loss,
            "risk_reward":     rr,
            "by_model":        by_model,
            "by_coin":         by_coin,
            "kalshi_total":    k_total,
            "kalshi_wins":     k_wins,
            "kalshi_win_rate": round(k_wins/k_closed*100,1) if k_closed > 0 else 0,
            "kalshi_pnl":      round(k_pnl, 2) if k_pnl else 0,
            "phase1_complete": ready_for_phase2,
            "phase1_note":     "Need 50+ closed trades, ≥48% win rate, ≥1.8 R:R to advance" if not ready_for_phase2 else "✅ Phase 1 criteria met — ready for paper trading",
        }

# Run init on import
init_db()
