# ================================================================
# MATHIAS QUANT BOT - PARTIE 2/3
# ICT + SMC + Carmona + Scoring
# Fichier : strategy.py
# ================================================================

from config_data import *

# ================================================================
# ICT — KILL ZONES
# ================================================================
def check_kill_zone():
    h = datetime.now(timezone.utc).hour
    for start, end, name in CONFIG["KILL_ZONES"]:
        if start <= h < end:
            return True, name
    return False, "HORS_KZ"

# ================================================================
# ICT — SWING HIGHS / LOWS
# ================================================================
def find_swings(df, n=10):
    hi = df["high"].values
    lo = df["low"].values
    sh = sl = None
    for i in range(len(hi)-2, max(len(hi)-n-1, 2), -1):
        i2 = min(i+1, len(hi)-1)
        if sh is None and hi[i] > hi[i-1] and hi[i] > hi[i2]:
            sh = hi[i]
        if sl is None and lo[i] < lo[i-1] and lo[i] < lo[i2]:
            sl = lo[i]
        if sh and sl:
            break
    return {"sh": sh, "sl": sl}

# ================================================================
# ICT — ORDER BLOCKS
# ================================================================
def find_order_blocks(df, n=20):
    atr = df["atr"].iloc[-1]
    res = {"bull": None, "bear": None}
    for i in range(len(df)-3, max(len(df)-n, 2), -1):
        c  = df.iloc[i]
        nx = df.iloc[i+1]
        if res["bull"] is None:
            if c["close"] < c["open"] and (nx["close"]-c["close"]) > atr*1.5:
                res["bull"] = {
                    "high": c["high"], "low": c["low"],
                    "mid":  (c["high"]+c["low"])/2
                }
        if res["bear"] is None:
            if c["close"] > c["open"] and (c["close"]-nx["close"]) > atr*1.5:
                res["bear"] = {
                    "high": c["high"], "low": c["low"],
                    "mid":  (c["high"]+c["low"])/2
                }
        if res["bull"] and res["bear"]:
            break
    return res

# ================================================================
# ICT — FAIR VALUE GAPS
# ================================================================
def find_fvg(df, n=15):
    res = {"bull": None, "bear": None}
    atr = df["atr"].iloc[-1]
    for i in range(max(2, len(df)-n), len(df)-1):
        b1 = df.iloc[i-2]
        b3 = df.iloc[i]
        if b3["low"] > b1["high"] and (b3["low"]-b1["high"]) > atr*0.3:
            res["bull"] = {
                "top": b3["low"], "bot": b1["high"],
                "mid": (b3["low"]+b1["high"])/2
            }
        elif b3["high"] < b1["low"] and (b1["low"]-b3["high"]) > atr*0.3:
            res["bear"] = {
                "top": b1["low"], "bot": b3["high"],
                "mid": (b1["low"]+b3["high"])/2
            }
    return res

# ================================================================
# ICT — LIQUIDITY SWEEP
# ================================================================
def check_sweep(df, sw):
    res = {"bull": False, "bear": False, "level": None}
    if len(df) < 5:
        return res
    rec = df.tail(5)
    p   = df["close"].iloc[-1]
    if sw["sl"] and rec["low"].min() < sw["sl"] and p > sw["sl"]:
        res["bull"]  = True
        res["level"] = sw["sl"]
    if sw["sh"] and rec["high"].max() > sw["sh"] and p < sw["sh"]:
        res["bear"]  = True
        res["level"] = sw["sh"]
    return res

# ================================================================
# DÉTECTEUR DE RÉGIME MARKOV
# ================================================================
def detect_regime(df):
    last   = df.iloc[-1]
    p      = last["close"]
    e50    = last["ema50"]
    e200   = last["ema200"]
    rsi    = last["rsi"]
    hist   = last["macd_hist"]
    bw     = last["bb_width"]
    bw_avg = df["bb_width"].rolling(50).mean().iloc[-1]

    if bw < bw_avg * 0.65:
        return "SQUEEZE", 0.50
    if p > e50 > e200 and rsi > 52 and hist > 0:
        return "BULL", 0.70
    if p < e50 < e200 and rsi < 48 and hist < 0:
        return "BEAR", 0.70
    return "RANGE", 0.50

# ================================================================
# MODULES CARMONA
# ================================================================
def carmona_var(df, confidence=0.95):
    returns = df["returns"].dropna().values
    if len(returns) < 30:
        return 0.02
    try:
        params = stats.t.fit(returns)
        var    = abs(stats.t.ppf(1-confidence, *params))
        return round(min(max(var, 0.005), 0.15), 4)
    except:
        return round(abs(np.percentile(returns, (1-confidence)*100)), 4)

def carmona_kelly(win_rate=0.55, rr=2.0):
    p = win_rate
    q = 1 - p
    b = rr
    if b <= 0:
        return 0.01
    kelly = (p * b - q) / b
    return round(max(min(kelly / 4, 0.03), 0.005), 4)

def carmona_copula(df, raw_score):
    if len(df) < 50 or raw_score < 2:
        return 1.0
    try:
        rsi_s  = df["rsi"].tail(50).values
        macd_s = df["macd_hist"].tail(50).values
        vol_s  = df["vol_ratio"].tail(50).values
        ema_s  = (df["close"] - df["ema50"]).tail(50).values
        pairs  = [
            (rsi_s, macd_s),
            (rsi_s, ema_s),
            (macd_s, vol_s),
        ]
        taus = []
        for x, y in pairs:
            tau, pval = stats.kendalltau(x, y)
            if pval < 0.05:
                taus.append(abs(tau))
        if not taus:
            return 1.0
        avg_tau    = np.mean(taus)
        multiplier = 1.0 + (avg_tau * raw_score / 10)
        return round(min(multiplier, 2.0), 3)
    except:
        return 1.0

# ================================================================
# CALCUL DU SCORE DE CONFLUENCE
# ================================================================
def calc_score(df, regime, kz_active, ob, fvg, sw, sweep):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    p    = last["close"]
    bull = 0
    bear = 0
    details = []

    # Kill Zone
    if kz_active:
        bull += 1; bear += 1
        details.append("OK Kill Zone active")
    else:
        details.append("-- Hors Kill Zone")

    # Régime
    if regime == "BULL":
        bull += 2
        details.append("OK Regime BULL")
    elif regime == "BEAR":
        bear += 2
        details.append("OK Regime BEAR")
    elif regime == "SQUEEZE":
        bull += 1; bear += 1
        details.append("OK SQUEEZE - explosion imminente")
    else:
        details.append("-- Regime RANGE neutre")

    # EMA
    e50  = last["ema50"]
    e200 = last["ema200"]
    if p > e50 > e200:
        bull += 2
        details.append("OK EMA BULL " + str(round(p)) +
                        ">" + str(round(e50)) + ">" + str(round(e200)))
    elif p < e50 < e200:
        bear += 2
        details.append("OK EMA BEAR")
    else:
        details.append("-- EMA non alignee")

    # RSI
    rsi = last["rsi"]
    if 50 < rsi < 70:
        bull += 1
        details.append("OK RSI haussier " + str(round(rsi,1)))
    elif 30 < rsi < 50:
        bear += 1
        details.append("OK RSI baissier " + str(round(rsi,1)))
    elif rsi <= 30:
        bull += 1
        details.append("OK RSI survente " + str(round(rsi,1)))
    elif rsi >= 70:
        bear += 1
        details.append("OK RSI surachat " + str(round(rsi,1)))
    else:
        details.append("-- RSI neutre " + str(round(rsi,1)))

    # MACD
    hist = last["macd_hist"]
    if hist > 0 and hist > prev["macd_hist"]:
        bull += 1
        details.append("OK MACD haussier " + str(round(hist,0)))
    elif hist < 0 and hist < prev["macd_hist"]:
        bear += 1
        details.append("OK MACD baissier " + str(round(hist,0)))
    else:
        details.append("-- MACD neutre " + str(round(hist,0)))

    # Order Block
    ob_bull = ob.get("bull")
    ob_bear = ob.get("bear")
    if ob_bull and ob_bull["low"] <= p <= ob_bull["high"] * 1.002:
        bull += 1
        details.append("OK Dans Bullish OB " +
                        str(round(ob_bull["low"])) + "-" +
                        str(round(ob_bull["high"])))
    elif ob_bear and ob_bear["low"]*0.998 <= p <= ob_bear["high"]:
        bear += 1
        details.append("OK Dans Bearish OB")
    else:
        details.append("-- Hors Order Block")

    # FVG
    fvg_b = fvg.get("bull")
    fvg_r = fvg.get("bear")
    if fvg_b and fvg_b["bot"] <= p <= fvg_b["top"]:
        bull += 1
        details.append("OK Dans Bullish FVG " +
                        str(round(fvg_b["bot"])) + "-" +
                        str(round(fvg_b["top"])))
    elif fvg_r and fvg_r["bot"] <= p <= fvg_r["top"]:
        bear += 1
        details.append("OK Dans Bearish FVG")
    else:
        details.append("-- Hors FVG")

    # Sweep
    if sweep["bull"]:
        bull += 1
        details.append("OK Bull sweep " +
                        str(round(sweep.get("level",0),0)))
    elif sweep["bear"]:
        bear += 1
        details.append("OK Bear sweep")
    else:
        details.append("-- Pas de sweep")

    # Volume
    vr = last["vol_ratio"]
    if vr > 1.3:
        details.append("OK Volume fort " + str(round(vr,1)) + "x")
    else:
        details.append("-- Volume faible " + str(round(vr,1)) + "x")

    # Bollinger
    if p <= last["bb_low"] * 1.002:
        bull += 1
        details.append("OK Sur bande basse Bollinger")
    elif p >= last["bb_up"] * 0.998:
        bear += 1
        details.append("OK Sur bande haute Bollinger")
    else:
        details.append("-- Dans les bandes Bollinger")

    # Décision
    if bull > bear and bull >= CONFIG["MIN_SCORE"]:
        return min(bull, 10), details, "LONG"
    elif bear > bull and bear >= CONFIG["MIN_SCORE"]:
        return min(bear, 10), details, "SHORT"
    return max(bull, bear), details, "NEUTRAL"

# ================================================================
# CALCUL SL / TP / TAILLE
# ================================================================
def calc_sl(entry, atr, ob, direction, regime):
    mult = {"BULL":1.8, "BEAR":1.8, "RANGE":1.5, "SQUEEZE":2.5}.get(regime, 2.0)
    buf  = 0.003
    if direction == "LONG":
        if ob and ob.get("bull"):
            return round(ob["bull"]["low"] * (1-buf), 2)
        return round(entry - atr * mult, 2)
    else:
        if ob and ob.get("bear"):
            return round(ob["bear"]["high"] * (1+buf), 2)
        return round(entry + atr * mult, 2)

def calc_tp(entry, sl, direction):
    risk = abs(entry - sl)
    if direction == "LONG":
        tp1 = round(entry + risk * 2.0, 2)
        tp2 = round(entry + risk * 3.0, 2)
    else:
        tp1 = round(entry - risk * 2.0, 2)
        tp2 = round(entry - risk * 3.0, 2)
    rr = round(abs(tp1-entry) / risk, 2) if risk > 0 else 0
    return tp1, tp2, rr

def calc_size(entry, sl, risk_pct):
    dist = abs(entry - sl)
    if dist == 0:
        return 0
    max_loss = CONFIG["CAPITAL"] * risk_pct
    return round(max_loss / dist, 6)

if __name__ == "__main__":
    write_log("Partie 2 chargee OK")
    write_log("ICT + Carmona + Scoring prets")
