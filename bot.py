# ================================================================
# MATHIAS QUANT BOT - PARTIE 3/3
# Bot principal + Dashboard + PythonAnywhere
# Fichier : bot.py
# ================================================================

from strategy import *

# ================================================================
# ANALYSE PRINCIPALE
# ================================================================
def run_analysis(journal):
    write_log("=" * 55)
    write_log("ANALYSE " + datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    write_log("=" * 55)

    # 1. Données
    df = get_candles(CONFIG["SYMBOL"], "1h", 300)
    df = add_indicators(df)

    last  = df.iloc[-1]
    price = last["close"]

    # 2. ICT
    kz_active, kz_name = check_kill_zone()
    regime, reg_prob   = detect_regime(df)
    sw    = find_swings(df)
    ob    = find_order_blocks(df)
    fvg   = find_fvg(df)
    sweep = check_sweep(df, sw)

    # 3. Carmona
    var_pct      = carmona_var(df, 0.95)
    kelly_pct    = carmona_kelly(0.55, CONFIG["MIN_RR"])
    dynamic_risk = min(kelly_pct, CONFIG["RISK"])
    copula_mult  = carmona_copula(df, 7)

    # 4. Affichage contexte
    write_log("Prix BTC   : " + str(round(price, 0)) + " $")
    write_log("Regime     : " + regime +
              " (" + str(round(reg_prob*100)) + "%)")
    write_log("Kill Zone  : " +
              ("ACTIVE " + kz_name if kz_active else "INACTIVE"))
    write_log("RSI        : " + str(round(last["rsi"], 1)))
    write_log("MACD hist  : " + str(round(last["macd_hist"], 0)))
    write_log("EMA 50/200 : " + str(round(last["ema50"],0)) +
              " / " + str(round(last["ema200"],0)))
    write_log("VaR 95%    : " + str(round(var_pct*100, 2)) + "% (Carmona)")
    write_log("Kelly opt  : " + str(round(dynamic_risk*100, 2)) + "%")

    if ob["bull"]:
        write_log("Bull OB    : " + str(round(ob["bull"]["low"])) +
                  " - " + str(round(ob["bull"]["high"])) + "$")
    if fvg["bull"]:
        write_log("Bull FVG   : " + str(round(fvg["bull"]["bot"])) +
                  " - " + str(round(fvg["bull"]["top"])) + "$")
    if sweep["bull"]:
        write_log("Sweep      : Bullish sweep detecte")

    # 5. Score
    raw_score, details, direction = calc_score(
        df, regime, kz_active, ob, fvg, sw, sweep)

    adj_score = round(min(raw_score * copula_mult, 10), 2)

    bar = "=" * raw_score + "-" * (10 - raw_score)
    write_log("-" * 55)
    write_log("SCORE RAW  : " + str(raw_score) + "/10  [" + bar + "]")
    write_log("COPULE     : x" + str(copula_mult) + " (Kendall)")
    write_log("SCORE ADJ  : " + str(adj_score) + "/10  (Carmona)")
    for d in details:
        write_log("  " + d)
    write_log("-" * 55)

    # 6. Signal et trade
    today = datetime.now().strftime("%Y-%m-%d")
    trades_today = len([t for t in journal if t.get("date") == today])

    if direction != "NEUTRAL" and adj_score >= CONFIG["MIN_SCORE"]:
        sl       = calc_sl(price, last["atr"], ob, direction, regime)
        tp1, tp2, rr = calc_tp(price, sl, direction)

        if rr >= CONFIG["MIN_RR"]:
            max_loss = round(CONFIG["CAPITAL"] * dynamic_risk, 2)
            size     = calc_size(price, sl, dynamic_risk)
            max_gain = round(max_loss * rr, 2)

            write_log("SIGNAL     : " + direction)
            write_log("Entree     : " + str(round(price, 0)) + " $")
            write_log("Stop Loss  : " + str(sl) +
                      " $ (-" + str(round(abs(price-sl)/price*100,1)) + "%)")
            write_log("TP1 50pct  : " + str(tp1) +
                      " $  R:R 1:" + str(rr))
            write_log("TP2 40pct  : " + str(tp2) + " $")
            write_log("Taille     : " + str(size) + " BTC")
            write_log("Risque     : " + str(max_loss) + " USDC")
            write_log("Gain TP1   : +" + str(max_gain) + " USDC")
            write_log("Mode       : " +
                      ("SIMULATION" if CONFIG["SIMULATION"] else "REEL"))

            if trades_today < CONFIG["MAX_TRADES"]:
                trade = {
                    "date":      today,
                    "time":      datetime.now().strftime("%H:%M"),
                    "direction": direction,
                    "entry":     round(price, 0),
                    "sl":        sl,
                    "tp1":       tp1,
                    "tp2":       tp2,
                    "rr":        rr,
                    "score":     adj_score,
                    "regime":    regime,
                    "kz":        kz_name,
                    "var":       var_pct,
                    "kelly":     dynamic_risk,
                    "size":      size,
                    "result":    "OPEN",
                    "pnl":       0.0
                }
                journal = add_trade(journal, trade)
                write_log("Journal : Trade #" + str(len(journal)) + " enregistre")

                # Email signal
                body = (
                    "SIGNAL " + direction + " detecte\n\n"
                    "Date     : " + today + " " + datetime.now().strftime("%H:%M") + "\n"
                    "BTC      : " + str(round(price,0)) + " $\n"
                    "Entree   : " + str(round(price,0)) + " $\n"
                    "SL       : " + str(sl) + " $\n"
                    "TP1      : " + str(tp1) + " $\n"
                    "TP2      : " + str(tp2) + " $\n"
                    "R:R      : 1:" + str(rr) + "\n"
                    "Score    : " + str(adj_score) + "/10\n"
                    "Regime   : " + regime + "\n"
                    "Risque   : " + str(max_loss) + " USDC\n"
                    "Gain TP1 : +" + str(max_gain) + " USDC\n"
                    "Mode     : " + ("SIMULATION" if CONFIG["SIMULATION"] else "REEL")
                )
                send_alert("SIGNAL " + direction + " | BTC " +
                           str(round(price,0)) + "$ | Score " +
                           str(adj_score), body)

                # Ordre réel si mode activé
                if not CONFIG["SIMULATION"]:
                    side = "BUY" if direction == "LONG" else "SELL"
                    order = place_order(side, size)
                    write_log("Ordre envoye : " + str(order.get("orderId")))
            else:
                write_log("Limite " + str(CONFIG["MAX_TRADES"]) +
                          " trades/jour atteinte")
        else:
            write_log("Score OK (" + str(adj_score) +
                      ") mais R:R=" + str(rr) + " insuffisant")
    else:
        write_log("PAS DE SIGNAL | Score " +
                  str(adj_score) + "/10 | " + direction)

    # 7. Fear & Greed
    fg_val, fg_label = get_fear_greed()
    write_log("Fear&Greed : " + str(fg_val) + " - " + fg_label)
    write_log("Trades aujourd'hui : " +
              str(trades_today) + "/" + str(CONFIG["MAX_TRADES"]))
    write_log("=" * 55)

    return journal

# ================================================================
# MISE À JOUR DES TRADES OUVERTS
# ================================================================
def update_open_trades(journal):
    try:
        df = get_candles(CONFIG["SYMBOL"], "1h", 10)
        price = df["close"].iloc[-1]
        updated = False

        for t in journal:
            if t.get("result") != "OPEN":
                continue

            direction = t.get("direction")
            tp1  = t.get("tp1", 0)
            sl   = t.get("sl", 0)
            size = t.get("size", 0)
            max_loss = CONFIG["CAPITAL"] * t.get("kelly", CONFIG["RISK"])

            if direction == "LONG":
                if price >= tp1:
                    t["result"] = "WIN"
                    t["pnl"]    = round(max_loss * t.get("rr", 2), 2)
                    t["exit"]   = round(price, 0)
                    write_log("WIN : Trade " + t["time"] +
                              " | TP1 atteint | +" + str(t["pnl"]) + " USDC")
                    send_alert(
                        "WIN +"+str(t["pnl"])+" USDC",
                        "TP1 atteint sur LONG BTC\n"
                        "Entree : " + str(t["entry"]) + "$\n"
                        "Sortie : " + str(round(price,0)) + "$\n"
                        "Gain   : +" + str(t["pnl"]) + " USDC"
                    )
                    updated = True
                elif price <= sl:
                    t["result"] = "LOSS"
                    t["pnl"]    = -round(max_loss, 2)
                    t["exit"]   = round(price, 0)
                    write_log("LOSS : Trade " + t["time"] +
                              " | SL touche | " + str(t["pnl"]) + " USDC")
                    send_alert(
                        "LOSS "+str(t["pnl"])+" USDC",
                        "Stop Loss touche sur LONG BTC\n"
                        "Entree : " + str(t["entry"]) + "$\n"
                        "Sortie : " + str(round(price,0)) + "$\n"
                        "Perte  : " + str(t["pnl"]) + " USDC"
                    )
                    updated = True

            elif direction == "SHORT":
                if price <= tp1:
                    t["result"] = "WIN"
                    t["pnl"]    = round(max_loss * t.get("rr", 2), 2)
                    t["exit"]   = round(price, 0)
                    write_log("WIN : Trade " + t["time"] +
                              " | TP1 atteint | +" + str(t["pnl"]) + " USDC")
                    updated = True
                elif price >= sl:
                    t["result"] = "LOSS"
                    t["pnl"]    = -round(max_loss, 2)
                    t["exit"]   = round(price, 0)
                    write_log("LOSS : Trade " + t["time"] +
                              " | SL touche | " + str(t["pnl"]) + " USDC")
                    updated = True

        if updated:
            save_journal(journal)

    except Exception as e:
        write_log("Erreur update trades : " + str(e), "ERROR")

    return journal

# ================================================================
# DASHBOARD — RAPPORT COMPLET
# ================================================================
def print_dashboard(journal):
    s = get_stats(journal)
    sep = "=" * 55

    write_log(sep)
    write_log("DASHBOARD MATHIAS QUANT BOT")
    write_log(datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    write_log(sep)
    write_log("CAPITAL INITIAL  : " + str(CONFIG["CAPITAL"]) + " USDC")
    write_log("CAPITAL ACTUEL   : " + str(s["capital"]) + " USDC")
    write_log("P&L TOTAL        : " + str(s["pnl"]) + " USDC")
    write_log(sep)
    write_log("TRADES TOTAL     : " + str(s["total"]))
    write_log("TRADES FERMES    : " + str(s["closed"]))
    write_log("TRADES OUVERTS   : " + str(s["open"]))
    write_log("WINS             : " + str(s["wins"]))
    write_log("LOSSES           : " + str(s["losses"]))
    if s["closed"] > 0:
        write_log("WIN RATE         : " + str(round(s["wr"]*100, 1)) + "%")
        if s["wr"] >= 0.60:
            write_log("OBJECTIF 60% ATTEINT !")
        elif s["wr"] >= 0.50:
            write_log("Win Rate correct - continue")
        else:
            write_log("Win Rate faible - analyse les logs")
    write_log(sep)

    # Derniers trades
    if journal:
        write_log("DERNIERS TRADES :")
        for t in journal[-5:][::-1]:
            line = (
                t.get("date","?") + " " + t.get("time","?") +
                " | " + t.get("direction","?") +
                " | Entree:" + str(t.get("entry","?")) +
                "$ | TP1:" + str(t.get("tp1","?")) +
                "$ | R:R 1:" + str(t.get("rr","?")) +
                " | Score:" + str(t.get("score","?")) +
                " | " + t.get("result","OPEN") +
                " | PnL:" + str(t.get("pnl",0)) + "$"
            )
            write_log(line)
    write_log(sep)

# ================================================================
# EMAIL RAPPORT QUOTIDIEN
# ================================================================
def send_daily_report(journal):
    s = get_stats(journal)
    today_trades = [t for t in journal
                    if t.get("date") == datetime.now().strftime("%Y-%m-%d")]

    body = (
        "RAPPORT QUOTIDIEN - " +
        datetime.now().strftime("%d/%m/%Y") + "\n\n"
        "CAPITAL ACTUEL  : " + str(s["capital"]) + " USDC\n"
        "P&L AUJOURD'HUI : " +
        str(round(sum(t.get("pnl",0) for t in today_trades), 2)) +
        " USDC\n"
        "TRADES TOTAL    : " + str(s["total"]) + "\n"
        "WIN RATE        : " + str(round(s["wr"]*100,1)) + "%\n\n"
        "TRADES DU JOUR  : " + str(len(today_trades)) + "\n"
    )
    for t in today_trades:
        body += (
            "  " + t.get("time","?") +
            " " + t.get("direction","?") +
            " Score:" + str(t.get("score","?")) +
            " " + t.get("result","OPEN") +
            " PnL:" + str(t.get("pnl",0)) + "$\n"
        )

    send_email(
        "Rapport " + datetime.now().strftime("%d/%m/%Y") +
        " | P&L " + str(s["pnl"]) + " USDC",
        body
    )

# ================================================================
# BOUCLE PRINCIPALE — TOURNE EN CONTINU
# ================================================================
def run_bot():
    write_log("BOT DEMARRE")
    write_log("Mode       : " +
              ("SIMULATION" if CONFIG["SIMULATION"] else "REEL"))
    write_log("Capital    : " + str(CONFIG["CAPITAL"]) + " USDC")
    write_log("Symbol     : " + CONFIG["SYMBOL"])
    write_log("Check      : toutes les 5 minutes")

    send_alert(
        "Bot demarre",
        "Mathias Quant Bot demarre\n"
        "Mode : " + ("SIMULATION" if CONFIG["SIMULATION"] else "REEL") + "\n"
        "Capital : " + str(CONFIG["CAPITAL"]) + " USDC\n"
        "Heure : " + datetime.now().strftime("%d/%m/%Y %H:%M")
    )

    journal      = load_journal()
    last_report  = datetime.now().date()
    check_count  = 0

    while True:
        try:
            # Analyse toutes les 5 min
            journal = run_analysis(journal)
            journal = update_open_trades(journal)
            check_count += 1

            # Dashboard toutes les heures
            if check_count % 12 == 0:
                print_dashboard(journal)

            # Rapport quotidien
            today = datetime.now().date()
            if today != last_report:
                send_daily_report(journal)
                last_report = today
                write_log("Rapport quotidien envoye")

            write_log("Prochain check dans 5 min...")
            time.sleep(300)

        except KeyboardInterrupt:
            write_log("Bot arrete par utilisateur")
            print_dashboard(journal)
            send_alert("Bot arrete", "Bot arrete manuellement")
            break

        except Exception as e:
            write_log("ERREUR : " + str(e), "ERROR")
            send_alert("ERREUR BOT", "Erreur : " + str(e) +
                      "\nBot retry dans 60s")
            time.sleep(60)

# ================================================================
# POINT D'ENTRÉE
# ================================================================
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "--dashboard":
            journal = load_journal()
            print_dashboard(journal)

        elif sys.argv[1] == "--stats":
            journal = load_journal()
            print_stats(journal)

        elif sys.argv[1] == "--once":
            journal = load_journal()
            journal = run_analysis(journal)
            print_stats(journal)

        elif sys.argv[1] == "--reset":
            confirm = input("Effacer le journal ? (oui/non) : ")
            if confirm == "oui":
                save_journal([])
                write_log("Journal reinitialise")
    else:
        run_bot()
