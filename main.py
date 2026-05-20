# ================================================================
# MATHIAS QUANT BOT — VERSION RENDER
# Fichier unique : main.py
# Contient : Bot + Dashboard + Anti-sleep
# ================================================================

import pandas as pd
import numpy as np
import requests
import hmac as hmac_lib
import hashlib
import time
import smtplib
import json
import os
import threading
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from scipy import stats
from flask import Flask, jsonify, render_template_string

try:
    from hmmlearn import hmm
    HMM_OK = True
except:
    HMM_OK = False

app = Flask(__name__)

# ================================================================
# CONFIGURATION — MODIFIE VIA VARIABLES D'ENVIRONNEMENT RENDER
# ================================================================
CONFIG = {
    "CAPITAL":      float(os.environ.get("CAPITAL",      "680")),
    "RISK":         float(os.environ.get("RISK",         "0.01")),
    "MIN_RR":       float(os.environ.get("MIN_RR",       "2.0")),
    "MIN_SCORE":    int(os.environ.get("MIN_SCORE",      "6")),
    "MAX_TRADES":   int(os.environ.get("MAX_TRADES",     "2")),
    "SYMBOL":       os.environ.get("SYMBOL",             "BTCUSDC"),
    "SIMULATION":   os.environ.get("SIMULATION",         "true").lower() == "true",
    "API_KEY":      os.environ.get("BINANCE_API_KEY",    ""),
    "API_SECRET":   os.environ.get("BINANCE_API_SECRET", ""),
    "EMAIL_ACTIVE": os.environ.get("EMAIL_ACTIVE",       "false").lower() == "true",
    "EMAIL_FROM":   os.environ.get("EMAIL_FROM",         ""),
    "EMAIL_TO":     os.environ.get("EMAIL_TO",           ""),
    "EMAIL_PASS":   os.environ.get("EMAIL_PASS",         ""),
    "KILL_ZONES": [
        (6,  9,  "LONDON"),
        (11, 14, "NEW_YORK"),
        (19, 21, "NY_CLOSE"),
    ],
    "JOURNAL_FILE": "journal.json",
    "LOG_FILE":     "bot.log",
}

# ================================================================
# LOGS
# ================================================================
log_buffer = []

def write_log(msg, level="INFO"):
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = "[" + ts + "] [" + level + "] " + str(msg)
    print(line, flush=True)
    log_buffer.append(line)
    if len(log_buffer) > 200:
        log_buffer.pop(0)
    try:
        with open(CONFIG["LOG_FILE"], "a") as f:
            f.write(line + "\n")
    except:
        pass

# ================================================================
# EMAIL
# ================================================================
def send_email(subject, body):
    if not CONFIG["EMAIL_ACTIVE"]:
        return
    try:
        msg = MIMEMultipart()
        msg["From"]    = CONFIG["EMAIL_FROM"]
        msg["To"]      = CONFIG["EMAIL_TO"]
        msg["Subject"] = "[BOT] " + subject
        msg.attach(MIMEText(body, "plain"))
        s = smtplib.SMTP("smtp.gmail.com", 587)
        s.starttls()
        s.login(CONFIG["EMAIL_FROM"], CONFIG["EMAIL_PASS"])
        s.sendmail(CONFIG["EMAIL_FROM"], CONFIG["EMAIL_TO"], msg.as_string())
        s.quit()
        write_log("Email envoye : " + subject)
    except Exception as e:
        write_log("Email echec : " + str(e), "ERROR")

# ================================================================
# JOURNAL
# ================================================================
def load_journal():
    try:
        if os.path.exists(CONFIG["JOURNAL_FILE"]):
            with open(CONFIG["JOURNAL_FILE"], "r") as f:
                return json.load(f)
    except:
        pass
    return []

def save_journal(j):
    try:
        with open(CONFIG["JOURNAL_FILE"], "w") as f:
            json.dump(j, f, indent=2)
    except:
        pass

def get_stats(j):
    if not j:
        return {"total":0,"closed":0,"wins":0,"losses":0,
                "open":0,"wr":0.0,"pnl":0.0,
                "capital": CONFIG["CAPITAL"]}
    closed  = [t for t in j if t.get("result") in ["WIN","LOSS"]]
    wins    = [t for t in closed if t.get("result") == "WIN"]
    losses  = [t for t in closed if t.get("result") == "LOSS"]
    pnl     = round(sum(t.get("pnl", 0) for t in closed), 2)
    wr      = round(len(wins)/len(closed)*100, 1) if closed else 0.0
    return {
        "total":   len(j),
        "closed":  len(closed),
        "wins":    len(wins),
        "losses":  len(losses),
        "open":    len(j) - len(closed),
        "wr":      wr,
        "pnl":     pnl,
        "capital": round(CONFIG["CAPITAL"] + pnl, 2),
    }

# ================================================================
# DONNÉES BINANCE
# ================================================================
def get_candles(symbol="BTCUSDC", interval="1h", limit=300):
    url    = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        r    = requests.get(url, params=params, timeout=15)
        data = r.json()
        if isinstance(data, dict) and data.get("code"):
            raise Exception(str(data.get("msg")))
        df = pd.DataFrame(data, columns=[
            "ts","open","high","low","close","vol",
            "ct","qv","n","tbv","tqv","ig"])
        for col in ["open","high","low","close","vol"]:
            df[col] = df[col].astype(float)
        df["ts"] = pd.to_datetime(df["ts"], unit="ms")
        write_log("Donnees OK : " + str(len(df)) + " bougies | BTC : " +
                  str(round(df["close"].iloc[-1], 0)) + "$")
        return df
    except Exception as e:
        write_log("Binance erreur : " + str(e) + " - simulation", "WARNING")
        np.random.seed(int(time.time()) % 999)
        p = 82000.0
        prices = []
        for _ in range(limit):
            p = max(p * (1 + np.random.normal(0, 0.008)), 10000)
            prices.append(p)
        return pd.DataFrame({
            "ts":    pd.date_range(end=datetime.now(), periods=limit, freq="1h"),
            "open":  [x*(1+np.random.uniform(-0.003,0.003)) for x in prices],
            "high":  [x*(1+abs(np.random.normal(0,0.006))) for x in prices],
            "low":   [x*(1-abs(np.random.normal(0,0.006))) for x in prices],
            "close": prices,
            "vol":   list(np.random.uniform(0.1, 2.0, limit)),
            "vq":    [x*100 for x in prices]
        })

def place_order(side, quantity):
    if CONFIG["SIMULATION"]:
        write_log("SIM - Ordre " + side + " " + str(round(quantity,6)) + " BTC")
        return {"orderId": "SIM_"+str(int(time.time())), "status":"FILLED"}
    try:
        url = "https://api.binance.com/api/v3/order"
        ts  = int(time.time() * 1000)
        params = {
            "symbol":    CONFIG["SYMBOL"],
            "side":      side,
            "type":      "MARKET",
            "quantity":  round(quantity, 5),
            "timestamp": ts,
            "recvWindow":5000
        }
        query = "&".join([str(k)+"="+str(v) for k,v in sorted(params.items())])
        sig = hmac_lib.new(
            CONFIG["API_SECRET"].encode(),
            query.encode(), hashlib.sha256).hexdigest()
        params["signature"] = sig
        r = requests.post(url, params=params,
                          headers={"X-MBX-APIKEY": CONFIG["API_KEY"]},
                          timeout=15)
        return r.json()
    except Exception as e:
        write_log("Ordre ECHEC : " + str(e), "ERROR")
        send_email("ERREUR ORDRE", str(e))
        return {}

# ================================================================
# INDICATEURS
# ================================================================
def add_indicators(df):
    c = df["close"]
    df["ema50"]   = c.ewm(span=50,  adjust=False).mean()
    df["ema200"]  = c.ewm(span=200, adjust=False).mean()
    delta = c.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    df["rsi"]       = 100 - 100/(1 + gain/loss.replace(0, np.nan))
    e12             = c.ewm(span=12, adjust=False).mean()
    e26             = c.ewm(span=26, adjust=False).mean()
    df["macd"]      = e12 - e26
    df["macd_sig"]  = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_sig"]
    mid             = c.rolling(20).mean()
    std             = c.rolling(20).std()
    df["bb_up"]     = mid + 2*std
    df["bb_mid"]    = mid
    df["bb_low"]    = mid - 2*std
    df["bb_width"]  = (df["bb_up"] - df["bb_low"]) / mid
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"]  - df["close"].shift()).abs()
    df["atr"]       = pd.concat([hl,hc,lc],axis=1).max(axis=1).rolling(14).mean()
    df["vol_ratio"] = df["vol"] / df["vol"].rolling(20).mean()
    df["returns"]   = c.pct_change()
    df["log_ret"]   = np.log(c / c.shift(1))
    df["volatility"]= df["returns"].rolling(14).std()
    return df.dropna()

# ================================================================
# ICT
# ================================================================
def check_kill_zone():
    h = datetime.now(timezone.utc).hour
    for s, e, name in CONFIG["KILL_ZONES"]:
        if s <= h < e:
            return True, name
    return False, "HORS_KZ"

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

def find_ob(df, n=20):
    atr = df["atr"].iloc[-1]
    res = {"bull": None, "bear": None}
    for i in range(len(df)-3, max(len(df)-n, 2), -1):
        c = df.iloc[i]; nx = df.iloc[i+1]
        if res["bull"] is None:
            if c["close"] < c["open"] and (nx["close"]-c["close"]) > atr*1.5:
                res["bull"] = {"high":c["high"],"low":c["low"]}
        if res["bear"] is None:
            if c["close"] > c["open"] and (c["close"]-nx["close"]) > atr*1.5:
                res["bear"] = {"high":c["high"],"low":c["low"]}
        if res["bull"] and res["bear"]:
            break
    return res

def find_fvg(df, n=15):
    res = {"bull": None, "bear": None}
    atr = df["atr"].iloc[-1]
    for i in range(max(2, len(df)-n), len(df)-1):
        b1 = df.iloc[i-2]; b3 = df.iloc[i]
        if b3["low"] > b1["high"] and (b3["low"]-b1["high"]) > atr*0.3:
            res["bull"] = {"top":b3["low"],"bot":b1["high"]}
        elif b3["high"] < b1["low"] and (b1["low"]-b3["high"]) > atr*0.3:
            res["bear"] = {"top":b1["low"],"bot":b3["high"]}
    return res

def check_sweep(df, sw):
    res = {"bull":False,"bear":False,"level":None}
    if len(df) < 5: return res
    rec = df.tail(5); p = df["close"].iloc[-1]
    if sw["sl"] and rec["low"].min() < sw["sl"] and p > sw["sl"]:
        res["bull"] = True; res["level"] = sw["sl"]
    if sw["sh"] and rec["high"].max() > sw["sh"] and p < sw["sh"]:
        res["bear"] = True; res["level"] = sw["sh"]
    return res

def detect_regime(df):
    last = df.iloc[-1]
    p,e50,e200 = last["close"],last["ema50"],last["ema200"]
    rsi,hist   = last["rsi"],last["macd_hist"]
    bw         = last["bb_width"]
    bw_avg     = df["bb_width"].rolling(50).mean().iloc[-1]
    if bw < bw_avg*0.65:           return "SQUEEZE", 0.50
    if p>e50>e200 and rsi>52 and hist>0: return "BULL", 0.70
    if p<e50<e200 and rsi<48 and hist<0: return "BEAR", 0.70
    return "RANGE", 0.50

# ================================================================
# CARMONA
# ================================================================
def carmona_var(df):
    r = df["returns"].dropna().values
    if len(r) < 30: return 0.02
    try:
        p = stats.t.fit(r)
        return round(min(max(abs(stats.t.ppf(0.05, *p)), 0.005), 0.15), 4)
    except:
        return round(abs(np.percentile(r, 5)), 4)

def carmona_kelly(wr=0.55, rr=2.0):
    k = (wr*rr - (1-wr)) / rr
    return round(max(min(k/4, 0.03), 0.005), 4)

def carmona_copula(df, raw_score):
    if len(df) < 50 or raw_score < 2: return 1.0
    try:
        pairs = [
            (df["rsi"].tail(50).values, df["macd_hist"].tail(50).values),
            (df["rsi"].tail(50).values, (df["close"]-df["ema50"]).tail(50).values),
        ]
        taus = [abs(stats.kendalltau(x,y)[0])
                for x,y in pairs
                if stats.kendalltau(x,y)[1] < 0.05]
        if not taus: return 1.0
        return round(min(1.0 + np.mean(taus)*raw_score/10, 2.0), 3)
    except:
        return 1.0

# ================================================================
# SCORE
# ================================================================
def calc_score(df, regime, kz, ob, fvg, sw, sweep):
    last = df.iloc[-1]; prev = df.iloc[-2]
    p    = last["close"]
    bull = bear = 0
    det  = []

    if kz:  bull+=1; bear+=1; det.append("OK Kill Zone active")
    else:   det.append("-- Hors Kill Zone")

    if regime=="BULL":    bull+=2; det.append("OK Regime BULL")
    elif regime=="BEAR":  bear+=2; det.append("OK Regime BEAR")
    elif regime=="SQUEEZE": bull+=1; bear+=1; det.append("OK SQUEEZE")
    else: det.append("-- RANGE neutre")

    e50,e200 = last["ema50"],last["ema200"]
    if p>e50>e200:   bull+=2; det.append("OK EMA BULL "+str(round(p))+">" +str(round(e50))+">"+str(round(e200)))
    elif p<e50<e200: bear+=2; det.append("OK EMA BEAR")
    else: det.append("-- EMA non alignee")

    rsi = last["rsi"]
    if 50<rsi<70:   bull+=1; det.append("OK RSI haussier "+str(round(rsi,1)))
    elif 30<rsi<50: bear+=1; det.append("OK RSI baissier "+str(round(rsi,1)))
    elif rsi<=30:   bull+=1; det.append("OK RSI survente "+str(round(rsi,1)))
    elif rsi>=70:   bear+=1; det.append("OK RSI surachat "+str(round(rsi,1)))
    else: det.append("-- RSI neutre "+str(round(rsi,1)))

    h = last["macd_hist"]
    if h>0 and h>prev["macd_hist"]:   bull+=1; det.append("OK MACD haussier")
    elif h<0 and h<prev["macd_hist"]: bear+=1; det.append("OK MACD baissier")
    else: det.append("-- MACD neutre")

    ob_b = ob.get("bull"); ob_r = ob.get("bear")
    if ob_b and ob_b["low"]<=p<=ob_b["high"]*1.002:
        bull+=1; det.append("OK Bullish OB "+str(round(ob_b["low"]))+"-"+str(round(ob_b["high"])))
    elif ob_r and ob_r["low"]*0.998<=p<=ob_r["high"]:
        bear+=1; det.append("OK Bearish OB")
    else: det.append("-- Hors OB")

    fvg_b = fvg.get("bull"); fvg_r = fvg.get("bear")
    if fvg_b and fvg_b["bot"]<=p<=fvg_b["top"]:
        bull+=1; det.append("OK Bullish FVG "+str(round(fvg_b["bot"]))+"-"+str(round(fvg_b["top"])))
    elif fvg_r and fvg_r["bot"]<=p<=fvg_r["top"]:
        bear+=1; det.append("OK Bearish FVG")
    else: det.append("-- Hors FVG")

    if sweep["bull"]:   bull+=1; det.append("OK Bull sweep "+str(round(sweep.get("level",0),0)))
    elif sweep["bear"]: bear+=1; det.append("OK Bear sweep")
    else: det.append("-- Pas de sweep")

    det.append(("OK" if last["vol_ratio"]>1.3 else "--") +
               " Volume "+str(round(last["vol_ratio"],1))+"x")

    if p<=last["bb_low"]*1.002:   bull+=1; det.append("OK Bande basse BB")
    elif p>=last["bb_up"]*0.998:  bear+=1; det.append("OK Bande haute BB")
    else: det.append("-- Dans les bandes BB")

    if bull>bear and bull>=CONFIG["MIN_SCORE"]:   return min(bull,10),det,"LONG"
    elif bear>bull and bear>=CONFIG["MIN_SCORE"]: return min(bear,10),det,"SHORT"
    return max(bull,bear),det,"NEUTRAL"

def calc_sl(entry, atr, ob, direction, regime):
    mult = {"BULL":1.8,"BEAR":1.8,"RANGE":1.5,"SQUEEZE":2.5}.get(regime,2.0)
    buf  = 0.003
    if direction=="LONG":
        if ob and ob.get("bull"): return round(ob["bull"]["low"]*(1-buf),2)
        return round(entry - atr*mult, 2)
    else:
        if ob and ob.get("bear"): return round(ob["bear"]["high"]*(1+buf),2)
        return round(entry + atr*mult, 2)

def calc_tp(entry, sl, direction):
    risk = abs(entry-sl)
    if direction=="LONG":
        tp1 = round(entry+risk*2.0,2); tp2 = round(entry+risk*3.0,2)
    else:
        tp1 = round(entry-risk*2.0,2); tp2 = round(entry-risk*3.0,2)
    rr = round(abs(tp1-entry)/risk,2) if risk>0 else 0
    return tp1,tp2,rr

# ================================================================
# MISE À JOUR TRADES OUVERTS
# ================================================================
def update_trades(journal):
    try:
        df    = get_candles(CONFIG["SYMBOL"],"1h",5)
        price = df["close"].iloc[-1]
        changed = False
        for t in journal:
            if t.get("result") != "OPEN": continue
            d   = t.get("direction")
            tp1 = t.get("tp1",0)
            sl  = t.get("sl",0)
            ml  = CONFIG["CAPITAL"] * t.get("kelly", CONFIG["RISK"])
            if d=="LONG":
                if price>=tp1:
                    t["result"]="WIN"; t["pnl"]=round(ml*t.get("rr",2),2)
                    t["exit"]=round(price,0); changed=True
                    write_log("WIN +"+str(t["pnl"])+" USDC | LONG TP1 "+str(tp1))
                    send_email("WIN +"+str(t["pnl"])+" USDC",
                               "LONG TP1 atteint\nEntree:"+str(t["entry"])+"$\nSortie:"+str(round(price,0))+"$")
                elif price<=sl:
                    t["result"]="LOSS"; t["pnl"]=-round(ml,2)
                    t["exit"]=round(price,0); changed=True
                    write_log("LOSS "+str(t["pnl"])+" USDC | SL "+str(sl))
                    send_email("LOSS "+str(t["pnl"])+" USDC",
                               "LONG SL touche\nEntree:"+str(t["entry"])+"$\nSortie:"+str(round(price,0))+"$")
            elif d=="SHORT":
                if price<=tp1:
                    t["result"]="WIN"; t["pnl"]=round(ml*t.get("rr",2),2)
                    t["exit"]=round(price,0); changed=True
                    write_log("WIN +"+str(t["pnl"])+" USDC | SHORT TP1")
                elif price>=sl:
                    t["result"]="LOSS"; t["pnl"]=-round(ml,2)
                    t["exit"]=round(price,0); changed=True
                    write_log("LOSS "+str(t["pnl"])+" USDC | SL")
        if changed: save_journal(journal)
    except Exception as e:
        write_log("Update trades erreur : "+str(e),"ERROR")
    return journal

# ================================================================
# ANALYSE PRINCIPALE
# ================================================================
def run_analysis(journal):
    write_log("="*50)
    write_log("ANALYSE "+datetime.now().strftime("%d/%m/%Y %H:%M:%S"))

    df     = get_candles(CONFIG["SYMBOL"],"1h",300)
    df     = add_indicators(df)
    last   = df.iloc[-1]
    price  = last["close"]

    kz_active, kz_name = check_kill_zone()
    regime, reg_prob   = detect_regime(df)
    sw     = find_swings(df)
    ob     = find_ob(df)
    fvg    = find_fvg(df)
    sweep  = check_sweep(df, sw)

    var_p    = carmona_var(df)
    kelly_p  = carmona_kelly(0.55, CONFIG["MIN_RR"])
    dyn_risk = min(kelly_p, CONFIG["RISK"])

    write_log("Prix:"+str(round(price,0))+"$ | Regime:"+regime+
              " | KZ:"+("OUI "+kz_name if kz_active else "NON")+
              " | RSI:"+str(round(last["rsi"],1))+
              " | MACD:"+str(round(last["macd_hist"],0)))

    raw, det, direction = calc_score(df, regime, kz_active, ob, fvg, sw, sweep)
    copula  = carmona_copula(df, raw)
    adj     = round(min(raw*copula, 10), 2)

    write_log("Score:"+str(raw)+"/10 | Copule:x"+str(copula)+" | Adj:"+str(adj)+"/10 | Dir:"+direction)
    for d in det: write_log("  "+d)

    today        = datetime.now().strftime("%Y-%m-%d")
    trades_today = len([t for t in journal if t.get("date")==today])

    if direction!="NEUTRAL" and adj>=CONFIG["MIN_SCORE"]:
        sl       = calc_sl(price, last["atr"], ob, direction, regime)
        tp1,tp2,rr = calc_tp(price, sl, direction)

        if rr >= CONFIG["MIN_RR"]:
            ml   = round(CONFIG["CAPITAL"]*dyn_risk, 2)
            size = round(ml/abs(price-sl), 6)
            gain = round(ml*rr, 2)

            write_log("SIGNAL "+direction+" | Entree:"+str(round(price,0))+
                      "$ | SL:"+str(sl)+"$ | TP1:"+str(tp1)+
                      "$ | R:R 1:"+str(rr)+" | Taille:"+str(size)+" BTC")

            if trades_today < CONFIG["MAX_TRADES"]:
                trade = {
                    "date": today,
                    "time": datetime.now().strftime("%H:%M"),
                    "direction": direction,
                    "entry": round(price,0),
                    "sl": sl, "tp1": tp1, "tp2": tp2,
                    "rr": rr, "score": adj,
                    "regime": regime, "kz": kz_name,
                    "kelly": dyn_risk, "size": size,
                    "result": "OPEN", "pnl": 0.0
                }
                journal.append(trade)
                save_journal(journal)
                write_log("Trade #"+str(len(journal))+" enregistre")

                send_email(
                    "SIGNAL "+direction+" | BTC "+str(round(price,0))+"$",
                    "Signal detecte\nDirection:"+direction+
                    "\nEntree:"+str(round(price,0))+"$"+
                    "\nSL:"+str(sl)+"$\nTP1:"+str(tp1)+
                    "$\nR:R 1:"+str(rr)+"\nScore:"+str(adj)+"/10"+
                    "\nRisque:-"+str(ml)+" USDC\nGain:+"+str(gain)+" USDC"
                )

                if not CONFIG["SIMULATION"]:
                    side  = "BUY" if direction=="LONG" else "SELL"
                    order = place_order(side, size)
                    write_log("Ordre: "+str(order.get("orderId"))+" "+str(order.get("status","")))
            else:
                write_log("Limite "+str(CONFIG["MAX_TRADES"])+" trades/jour atteinte")
        else:
            write_log("Score OK mais R:R="+str(rr)+" insuffisant")
    else:
        write_log("PAS DE SIGNAL | Score "+str(adj)+"/10 | "+direction)

    write_log("="*50)
    return journal

# ================================================================
# BOUCLE BOT EN ARRIÈRE-PLAN
# ================================================================
journal_global = load_journal()

def bot_loop():
    global journal_global
    write_log("BOT DEMARRE | Mode:"+("SIM" if CONFIG["SIMULATION"] else "REEL")+
              " | Capital:"+str(CONFIG["CAPITAL"])+" USDC")
    send_email("Bot demarre",
               "Mathias Quant Bot demarre\nMode:"+
               ("SIMULATION" if CONFIG["SIMULATION"] else "REEL")+
               "\nCapital:"+str(CONFIG["CAPITAL"])+" USDC")
    count = 0
    while True:
        try:
            journal_global = run_analysis(journal_global)
            journal_global = update_trades(journal_global)
            count += 1
            time.sleep(300)
        except Exception as e:
            write_log("ERREUR : "+str(e), "ERROR")
            send_email("ERREUR BOT", str(e))
            time.sleep(60)

# ================================================================
# DASHBOARD HTML
# ================================================================
HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="60">
<title>Mathias Quant Bot</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#080c10;color:#c8e0f4;font-family:'Courier New',monospace;font-size:13px;padding:12px}
.hdr{text-align:center;padding:16px;border-bottom:1px solid #1a3050;margin-bottom:16px}
.hdr h1{color:#00d4ff;font-size:20px;letter-spacing:2px}
.hdr p{color:#4a6a8a;font-size:10px;margin-top:4px}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:16px}
.kpi{background:#0a0e18;border:1px solid #1a3050;border-radius:6px;padding:12px;text-align:center}
.kpi-l{font-size:9px;color:#4a6a8a;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px}
.kpi-v{font-size:22px;font-weight:bold}
.green{color:#00e676}.red{color:#ff3366}.amber{color:#ffaa00}.blue{color:#00d4ff}.white{color:#fff}
.sec{background:#0a0e18;border:1px solid #1a3050;border-radius:6px;margin-bottom:12px;overflow:hidden}
.sec-t{padding:10px 14px;border-bottom:1px solid #1a3050;font-size:11px;color:#00d4ff;text-transform:uppercase;letter-spacing:1px}
.sec-b{padding:12px}
table{width:100%;border-collapse:collapse;font-size:10px}
th{padding:6px 4px;color:#4a6a8a;text-align:left;border-bottom:1px solid #1a3050;font-size:9px;text-transform:uppercase}
td{padding:6px 4px;border-bottom:1px solid #0f1a28}
tr:last-child td{border-bottom:none}
.bw,.bl,.bo,.bs{display:inline-block;padding:2px 6px;border-radius:3px;font-size:9px;font-weight:bold}
.bw{background:#003318;color:#00e676;border:1px solid #00e676}
.bl{background:#330011;color:#ff3366;border:1px solid #ff3366}
.bo{background:#332200;color:#ffaa00;border:1px solid #ffaa00}
.bs{background:#001a33;color:#00d4ff}
.log{background:#020406;border-radius:4px;padding:10px;font-size:10px;line-height:1.7;max-height:180px;overflow-y:auto;color:#4a6a8a}
.la{color:#ff3366}.ls{color:#00e676}.lw{color:#ffaa00}
.bar-w{background:#0f1a28;border-radius:4px;height:8px;margin-top:6px;overflow:hidden}
.bar-f{height:100%;border-radius:4px}
.bg{background:linear-gradient(90deg,#003318,#00e676)}
.ba{background:linear-gradient(90deg,#332200,#ffaa00)}
.br{background:linear-gradient(90deg,#330011,#ff3366)}
.note{text-align:center;font-size:9px;color:#1a3050;margin-top:12px}
@media(max-width:420px){.grid{grid-template-columns:repeat(2,1fr)}.kpi-v{font-size:18px}}
</style>
</head>
<body>
<div class="hdr">
  <h1>MATHIAS QUANT BOT</h1>
  <p>BTC/USDC · Binance · ICT+SMC+Carmona · {{ now }} · Auto-refresh 60s</p>
</div>
<div class="grid">
  <div class="kpi"><div class="kpi-l">Capital</div>
    <div class="kpi-v {{ 'green' if s.pnl >= 0 else 'red' }}">{{ s.capital }}$</div></div>
  <div class="kpi"><div class="kpi-l">P&L Total</div>
    <div class="kpi-v {{ 'green' if s.pnl >= 0 else 'red' }}">{{ '+' if s.pnl >= 0 else '' }}{{ s.pnl }}$</div></div>
  <div class="kpi"><div class="kpi-l">Win Rate</div>
    <div class="kpi-v {{ 'green' if s.wr >= 60 else 'amber' if s.wr >= 50 else 'red' }}">{{ s.wr }}%</div></div>
  <div class="kpi"><div class="kpi-l">Trades</div>
    <div class="kpi-v white">{{ s.total }}</div></div>
  <div class="kpi"><div class="kpi-l">W / L</div>
    <div class="kpi-v"><span class="green">{{ s.wins }}</span>/<span class="red">{{ s.losses }}</span></div></div>
  <div class="kpi"><div class="kpi-l">Ouverts</div>
    <div class="kpi-v amber">{{ s.open }}</div></div>
</div>
{% if s.closed > 0 %}
<div class="sec"><div class="sec-t">Progression Win Rate</div><div class="sec-b">
  <div style="display:flex;justify-content:space-between;font-size:10px;margin-bottom:4px">
    <span>{{ s.wr }}% actuel</span><span class="green">60% objectif</span></div>
  <div class="bar-w"><div class="bar-f {{ 'bg' if s.wr >= 60 else 'ba' if s.wr >= 50 else 'br' }}"
    style="width:{{ [s.wr,100]|min }}%"></div></div>
  <div style="text-align:center;font-size:9px;color:#4a6a8a;margin-top:6px">
    {% if s.wr >= 60 %}Objectif atteint — mode reel possible
    {% elif s.wr >= 50 %}Continue — {{ (60-s.wr)|round(1) }}% manquant
    {% else %}Sous objectif — analyse les logs{% endif %}</div>
</div></div>
{% endif %}
{% set opens = trades|selectattr("result","equalto","OPEN")|list %}
{% if opens %}
<div class="sec"><div class="sec-t">Positions Ouvertes ({{ opens|length }})</div><div class="sec-b">
<table><tr><th>Date</th><th>Dir</th><th>Entree</th><th>SL</th><th>TP1</th><th>R:R</th><th>Score</th></tr>
{% for t in opens %}
<tr>
  <td>{{ t.date }} {{ t.time }}</td>
  <td><span class="bs">{{ t.direction }}</span></td>
  <td class="white">{{ t.entry }}$</td>
  <td class="red">{{ t.sl }}$</td>
  <td class="green">{{ t.tp1 }}$</td>
  <td class="amber">1:{{ t.rr }}</td>
  <td class="blue">{{ t.score }}</td>
</tr>{% endfor %}
</table></div></div>{% endif %}
{% set closed = trades|selectattr("result","in",["WIN","LOSS"])|list %}
{% if closed %}
<div class="sec"><div class="sec-t">Historique ({{ closed|length }})</div><div class="sec-b">
<table><tr><th>Date</th><th>Dir</th><th>Entree</th><th>TP1</th><th>R:R</th><th>Res</th><th>PnL</th></tr>
{% for t in closed[-8:]|reverse %}
<tr>
  <td>{{ t.date }} {{ t.time }}</td>
  <td><span class="bs">{{ t.direction }}</span></td>
  <td class="white">{{ t.entry }}$</td>
  <td>{{ t.tp1 }}$</td>
  <td class="amber">1:{{ t.rr }}</td>
  <td><span class="{{ 'bw' if t.result=='WIN' else 'bl' }}">{{ t.result }}</span></td>
  <td class="{{ 'green' if t.pnl >= 0 else 'red' }}">{{ '+' if t.pnl >= 0 else '' }}{{ t.pnl }}$</td>
</tr>{% endfor %}
</table></div></div>{% endif %}
<div class="sec"><div class="sec-t">Logs en direct</div><div class="sec-b">
<div class="log">{% for l in logs %}
<div class="{{ 'la' if 'ERROR' in l or 'LOSS' in l else 'ls' if 'WIN' in l or 'SIGNAL' in l else 'lw' if 'WARNING' in l else '' }}">{{ l }}</div>
{% endfor %}</div></div></div>
<div class="note">Refresh auto 60s · {{ mode }}</div>
</body></html>"""

# ================================================================
# ROUTES FLASK
# ================================================================
@app.route("/")
def dashboard():
    j  = journal_global
    s  = get_stats(j)
    logs = log_buffer[-30:][::-1]
    now  = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    mode = "SIMULATION" if CONFIG["SIMULATION"] else "MODE REEL"
    return render_template_string(HTML, s=s, trades=j,
                                  logs=logs, now=now, mode=mode)

@app.route("/api/stats")
def api_stats():
    return jsonify(get_stats(journal_global))

@app.route("/api/trades")
def api_trades():
    return jsonify(journal_global)

@app.route("/ping")
def ping():
    return "OK " + datetime.now().strftime("%H:%M:%S")

# ================================================================
# LANCEMENT
# ================================================================
if __name__ == "__main__":
    # Lance le bot en arrière-plan
    t = threading.Thread(target=bot_loop, daemon=True)
    t.start()
    write_log("Dashboard Flask demarre")
    # Lance le serveur web
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
