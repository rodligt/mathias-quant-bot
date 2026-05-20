# ================================================================
# MATHIAS QUANT BOT - PARTIE 1/3
# Configuration + Données + Indicateurs
# Fichier : config_data.py
# ================================================================

import pandas as pd
import numpy as np
import requests
import hmac
import hashlib
import time
import smtplib
import json
import os
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from scipy import stats

try:
    from hmmlearn import hmm
    HMM_OK = True
except:
    HMM_OK = False

# ================================================================
# CONFIGURATION — MODIFIE UNIQUEMENT CETTE SECTION
# ================================================================
CONFIG = {
    # Capital et risque
    "CAPITAL":      680,
    "RISK":         0.01,
    "MIN_RR":       2.0,
    "MIN_SCORE":    6,
    "MAX_TRADES":   2,
    "SYMBOL":       "BTCUSDC",
    "SIMULATION":   True,    # False = ordres reels

    # Tes cles Binance — colle ici
    "API_KEY":      "COLLE_TA_CLE_ICI",
    "API_SECRET":   "COLLE_TON_SECRET_ICI",

    # Alertes email
    "EMAIL_ACTIVE": True,
    "EMAIL_FROM":   "ton_email@gmail.com",
    "EMAIL_TO":     "ton_email@gmail.com",
    "EMAIL_PASS":   "mot_de_passe_application_gmail",

    # Kill Zones UTC
    "KILL_ZONES": [
        (6,  9,  "LONDON"),
        (11, 14, "NEW_YORK"),
        (19, 21, "NY_CLOSE"),
    ],

    # Fichier journal
    "JOURNAL_FILE": "journal_trades.json",
    "LOG_FILE":     "bot_log.txt",
}

# ================================================================
# SYSTÈME DE LOGS ET ALERTES EMAIL
# ================================================================
def write_log(message, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = "[" + ts + "] [" + level + "] " + message
    print(line)
    try:
        with open(CONFIG["LOG_FILE"], "a") as f:
            f.write(line + "\n")
    except:
        pass

def send_email(subject, body):
    if not CONFIG["EMAIL_ACTIVE"]:
        return
    try:
        msg = MIMEMultipart()
        msg["From"]    = CONFIG["EMAIL_FROM"]
        msg["To"]      = CONFIG["EMAIL_TO"]
        msg["Subject"] = "[QUANT BOT] " + subject
        msg.attach(MIMEText(body, "plain"))
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(CONFIG["EMAIL_FROM"], CONFIG["EMAIL_PASS"])
        server.sendmail(CONFIG["EMAIL_FROM"], CONFIG["EMAIL_TO"], msg.as_string())
        server.quit()
        write_log("Email envoye : " + subject)
    except Exception as e:
        write_log("Email ECHEC : " + str(e), "ERROR")

def send_alert(subject, body):
    write_log("ALERTE : " + subject, "ALERT")
    send_email(subject, body)

# ================================================================
# JOURNAL DE TRADING
# ================================================================
def load_journal():
    try:
        if os.path.exists(CONFIG["JOURNAL_FILE"]):
            with open(CONFIG["JOURNAL_FILE"], "r") as f:
                return json.load(f)
    except:
        pass
    return []

def save_journal(journal):
    try:
        with open(CONFIG["JOURNAL_FILE"], "w") as f:
            json.dump(journal, f, indent=2)
    except Exception as e:
        write_log("Erreur sauvegarde journal : " + str(e), "ERROR")

def add_trade(journal, trade):
    journal.append(trade)
    save_journal(journal)
    return journal

def get_stats(journal):
    if not journal:
        return {"total": 0, "wins": 0, "losses": 0, "wr": 0, "pnl": 0.0}
    closed = [t for t in journal if t.get("result") in ["WIN", "LOSS"]]
    wins   = [t for t in closed if t.get("result") == "WIN"]
    losses = [t for t in closed if t.get("result") == "LOSS"]
    pnl    = sum(t.get("pnl", 0) for t in closed)
    wr     = len(wins) / len(closed) if closed else 0
    return {
        "total":   len(journal),
        "closed":  len(closed),
        "wins":    len(wins),
        "losses":  len(losses),
        "open":    len(journal) - len(closed),
        "wr":      round(wr, 3),
        "pnl":     round(pnl, 2),
        "capital": round(CONFIG["CAPITAL"] + pnl, 2),
    }

def print_stats(journal):
    s = get_stats(journal)
    write_log("=" * 50)
    write_log("STATISTIQUES BOT")
    write_log("Trades total  : " + str(s["total"]) +
              " (ouverts: " + str(s["open"]) + ")")
    write_log("Trades fermes : " + str(s["closed"]) +
              " | Wins: " + str(s["wins"]) +
              " | Losses: " + str(s["losses"]))
    if s["closed"] > 0:
        write_log("Win Rate      : " + str(round(s["wr"]*100, 1)) + "%")
    write_log("P&L total     : " + str(s["pnl"]) + " USDC")
    write_log("Capital actuel: " + str(s["capital"]) + " USDC")
    if s["wr"] >= 0.60:
        write_log("OBJECTIF WIN RATE 60% ATTEINT !", "SUCCESS")
    write_log("=" * 50)

# ================================================================
# RÉCUPÉRATION DONNÉES BINANCE
# ================================================================
def get_candles(symbol="BTCUSDC", interval="1h", limit=300):
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        if isinstance(data, dict) and data.get("code"):
            raise Exception(str(data.get("msg")))
        df = pd.DataFrame(data, columns=[
            "ts","open","high","low","close","vol",
            "close_time","qvol","ntrades","tbvol","tqvol","ignore"])
        for col in ["open","high","low","close","vol"]:
            df[col] = df[col].astype(float)
        df["ts"] = pd.to_datetime(df["ts"], unit="ms")
        write_log("Donnees OK : " + str(len(df)) +
                  " bougies | BTC : " + str(round(df["close"].iloc[-1], 0)) + "$")
        return df
    except Exception as e:
        write_log("API Binance erreur : " + str(e) + " - simulation", "WARNING")
        np.random.seed(int(time.time()) % 1000)
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

def get_fear_greed():
    try:
        r = requests.get(
            "https://api.alternative.me/fng/?limit=1", timeout=8)
        d = r.json()["data"][0]
        return int(d["value"]), d["value_classification"]
    except:
        return 50, "Neutral"

def place_order(side, quantity):
    if CONFIG["SIMULATION"]:
        msg = "SIMULATION - Ordre " + side + " " + str(round(quantity,6)) + " BTC"
        write_log(msg)
        return {"orderId": "SIM_" + str(int(time.time())), "status": "FILLED"}
    try:
        url = "https://api.binance.com/api/v3/order"
        ts  = int(time.time() * 1000)
        params = {
            "symbol":     CONFIG["SYMBOL"],
            "side":       side,
            "type":       "MARKET",
            "quantity":   round(quantity, 5),
            "timestamp":  ts,
            "recvWindow": 5000
        }
        query = "&".join([str(k)+"="+str(v) for k,v in sorted(params.items())])
        sig = hmac.new(
            CONFIG["API_SECRET"].encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        params["signature"] = sig
        headers = {"X-MBX-APIKEY": CONFIG["API_KEY"]}
        r = requests.post(url, params=params, headers=headers, timeout=15)
        result = r.json()
        write_log("Ordre Binance : " + str(result.get("orderId")) +
                  " | " + str(result.get("status")))
        return result
    except Exception as e:
        write_log("Ordre ECHEC : " + str(e), "ERROR")
        send_alert("ERREUR ORDRE", "Ordre " + side + " echoue : " + str(e))
        return {}

# ================================================================
# INDICATEURS TECHNIQUES
# ================================================================
def add_indicators(df):
    c = df["close"]
    df["ema50"]   = c.ewm(span=50,  adjust=False).mean()
    df["ema200"]  = c.ewm(span=200, adjust=False).mean()
    df["ema9"]    = c.ewm(span=9,   adjust=False).mean()
    delta = c.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    df["rsi"]       = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    ema12           = c.ewm(span=12, adjust=False).mean()
    ema26           = c.ewm(span=26, adjust=False).mean()
    df["macd"]      = ema12 - ema26
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

if __name__ == "__main__":
    write_log("Partie 1 chargee OK")
    df = get_candles()
    df = add_indicators(df)
    write_log("Test donnees OK - " + str(len(df)) + " bougies")
