# ================================================================
# MATHIAS QUANT BOT — DASHBOARD WEB
# Fichier : dashboard_web.py
# Lance avec : python dashboard_web.py
# Accessible sur : https://tonnom.pythonanywhere.com
# ================================================================

from flask import Flask, jsonify, render_template_string
import json
import os
from datetime import datetime

app = Flask(__name__)

JOURNAL_FILE = "journal_trades.json"
LOG_FILE     = "bot_log.txt"

def load_journal():
    try:
        if os.path.exists(JOURNAL_FILE):
            with open(JOURNAL_FILE, "r") as f:
                return json.load(f)
    except:
        pass
    return []

def load_logs(n=50):
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r") as f:
                lines = f.readlines()
                return lines[-n:]
    except:
        pass
    return []

def get_stats(journal):
    if not journal:
        return {
            "total":0,"closed":0,"wins":0,
            "losses":0,"open":0,"wr":0,"pnl":0,"capital":680
        }
    closed = [t for t in journal if t.get("result") in ["WIN","LOSS"]]
    wins   = [t for t in closed if t.get("result") == "WIN"]
    losses = [t for t in closed if t.get("result") == "LOSS"]
    pnl    = round(sum(t.get("pnl",0) for t in closed), 2)
    wr     = round(len(wins)/len(closed)*100, 1) if closed else 0
    return {
        "total":   len(journal),
        "closed":  len(closed),
        "wins":    len(wins),
        "losses":  len(losses),
        "open":    len(journal)-len(closed),
        "wr":      wr,
        "pnl":     pnl,
        "capital": round(680 + pnl, 2),
    }

HTML = """
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="60">
<title>Mathias Quant Bot</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body {
  background:#080c10;
  color:#c8e0f4;
  font-family: 'Courier New', monospace;
  padding:16px;
  font-size:14px;
}
.header {
  text-align:center;
  padding:20px;
  border-bottom:1px solid #1a3050;
  margin-bottom:20px;
}
.header h1 { color:#00d4ff; font-size:22px; letter-spacing:2px; }
.header p  { color:#4a6a8a; font-size:11px; margin-top:6px; }

.kpi-grid {
  display:grid;
  grid-template-columns: repeat(3,1fr);
  gap:10px;
  margin-bottom:20px;
}
.kpi {
  background:#0a0e18;
  border:1px solid #1a3050;
  border-radius:8px;
  padding:14px;
  text-align:center;
}
.kpi-label {
  font-size:10px;
  color:#4a6a8a;
  text-transform:uppercase;
  letter-spacing:1px;
  margin-bottom:8px;
}
.kpi-val {
  font-size:24px;
  font-weight:bold;
  letter-spacing:-0.5px;
}
.green  { color:#00e676; }
.red    { color:#ff3366; }
.amber  { color:#ffaa00; }
.blue   { color:#00d4ff; }
.white  { color:#ffffff; }

.section {
  background:#0a0e18;
  border:1px solid #1a3050;
  border-radius:8px;
  margin-bottom:16px;
  overflow:hidden;
}
.section-title {
  padding:12px 16px;
  border-bottom:1px solid #1a3050;
  font-size:12px;
  color:#00d4ff;
  text-transform:uppercase;
  letter-spacing:1px;
}
.section-body { padding:14px; }

table {
  width:100%;
  border-collapse:collapse;
  font-size:11px;
}
th {
  padding:8px 6px;
  color:#4a6a8a;
  text-align:left;
  border-bottom:1px solid #1a3050;
  font-size:10px;
  text-transform:uppercase;
}
td {
  padding:8px 6px;
  border-bottom:1px solid #0f1a28;
}
tr:last-child td { border-bottom:none; }

.badge {
  display:inline-block;
  padding:2px 8px;
  border-radius:3px;
  font-size:10px;
  font-weight:bold;
}
.badge-win   { background:#003318; color:#00e676; border:1px solid #00e676; }
.badge-loss  { background:#330011; color:#ff3366; border:1px solid #ff3366; }
.badge-open  { background:#332200; color:#ffaa00; border:1px solid #ffaa00; }
.badge-long  { background:#001833; color:#00d4ff; }
.badge-short { background:#1a0011; color:#ff6699; }

.log-box {
  background:#020406;
  border-radius:6px;
  padding:12px;
  font-size:11px;
  line-height:1.8;
  max-height:200px;
  overflow-y:auto;
  color:#6a90a8;
}
.log-alert  { color:#ff3366; }
.log-signal { color:#00e676; }
.log-warn   { color:#ffaa00; }

.bar-wrap {
  background:#0f1a28;
  border-radius:4px;
  height:8px;
  margin-top:6px;
  overflow:hidden;
}
.bar-fill {
  height:100%;
  border-radius:4px;
  transition:width 0.5s ease;
}
.bar-green { background:linear-gradient(90deg,#003318,#00e676); }
.bar-amber { background:linear-gradient(90deg,#332200,#ffaa00); }
.bar-red   { background:linear-gradient(90deg,#330011,#ff3366); }

.refresh-note {
  text-align:center;
  font-size:10px;
  color:#1a3050;
  margin-top:16px;
}

@media(max-width:500px){
  .kpi-grid { grid-template-columns:repeat(2,1fr); }
  .kpi-val  { font-size:18px; }
}
</style>
</head>
<body>

<div class="header">
  <h1>🤖 MATHIAS QUANT BOT</h1>
  <p>BTC/USDC · Binance · ICT + SMC + Carmona · {{ now }}</p>
</div>

<!-- KPI -->
<div class="kpi-grid">
  <div class="kpi">
    <div class="kpi-label">Capital</div>
    <div class="kpi-val {{ 'green' if stats.pnl >= 0 else 'red' }}">
      {{ stats.capital }} $
    </div>
  </div>
  <div class="kpi">
    <div class="kpi-label">P&L Total</div>
    <div class="kpi-val {{ 'green' if stats.pnl >= 0 else 'red' }}">
      {{ '+' if stats.pnl >= 0 else '' }}{{ stats.pnl }} $
    </div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Win Rate</div>
    <div class="kpi-val {{ 'green' if stats.wr >= 60 else 'amber' if stats.wr >= 50 else 'red' }}">
      {{ stats.wr }}%
    </div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Trades Total</div>
    <div class="kpi-val white">{{ stats.total }}</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Wins / Losses</div>
    <div class="kpi-val">
      <span class="green">{{ stats.wins }}</span>
      /
      <span class="red">{{ stats.losses }}</span>
    </div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Ouverts</div>
    <div class="kpi-val amber">{{ stats.open }}</div>
  </div>
</div>

<!-- BARRE DE PROGRESSION -->
{% if stats.closed > 0 %}
<div class="section">
  <div class="section-title">Progression Win Rate</div>
  <div class="section-body">
    <div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:4px">
      <span>{{ stats.wr }}% actuel</span>
      <span class="green">60% objectif</span>
    </div>
    <div class="bar-wrap">
      <div class="bar-fill {{ 'bar-green' if stats.wr >= 60 else 'bar-amber' if stats.wr >= 50 else 'bar-red' }}"
           style="width:{{ [stats.wr, 100]|min }}%"></div>
    </div>
    <div style="text-align:center;font-size:10px;color:#4a6a8a;margin-top:6px">
      {% if stats.wr >= 60 %}
        ✅ Objectif atteint — tu peux envisager le mode réel
      {% elif stats.wr >= 50 %}
        ⚠️ Continue — encore {{ 60 - stats.wr|round(1) }}% à gagner
      {% else %}
        ❌ Sous objectif — analyse les signaux
      {% endif %}
    </div>
  </div>
</div>
{% endif %}

<!-- TRADES OUVERTS -->
{% set open_trades = trades|selectattr("result","equalto","OPEN")|list %}
{% if open_trades %}
<div class="section">
  <div class="section-title">🟡 Positions Ouvertes ({{ open_trades|length }})</div>
  <div class="section-body">
    <table>
      <tr>
        <th>Date</th><th>Dir.</th><th>Entrée</th>
        <th>SL</th><th>TP1</th><th>R:R</th><th>Score</th>
      </tr>
      {% for t in open_trades %}
      <tr>
        <td>{{ t.date }} {{ t.time }}</td>
        <td>
          <span class="badge {{ 'badge-long' if t.direction=='LONG' else 'badge-short' }}">
            {{ t.direction }}
          </span>
        </td>
        <td class="white">{{ t.entry }}$</td>
        <td class="red">{{ t.sl }}$</td>
        <td class="green">{{ t.tp1 }}$</td>
        <td class="amber">1:{{ t.rr }}</td>
        <td class="blue">{{ t.score }}/10</td>
      </tr>
      {% endfor %}
    </table>
  </div>
</div>
{% endif %}

<!-- HISTORIQUE TRADES -->
{% set closed_trades = trades|selectattr("result","in",["WIN","LOSS"])|list %}
{% if closed_trades %}
<div class="section">
  <div class="section-title">📋 Historique ({{ closed_trades|length }} trades)</div>
  <div class="section-body">
    <table>
      <tr>
        <th>Date</th><th>Dir.</th><th>Entrée</th>
        <th>TP1</th><th>R:R</th><th>Résultat</th><th>P&L</th>
      </tr>
      {% for t in closed_trades[-10:]|reverse %}
      <tr>
        <td>{{ t.date }} {{ t.time }}</td>
        <td>
          <span class="badge {{ 'badge-long' if t.direction=='LONG' else 'badge-short' }}">
            {{ t.direction }}
          </span>
        </td>
        <td class="white">{{ t.entry }}$</td>
        <td>{{ t.tp1 }}$</td>
        <td class="amber">1:{{ t.rr }}</td>
        <td>
          <span class="badge {{ 'badge-win' if t.result=='WIN' else 'badge-loss' }}">
            {{ t.result }}
          </span>
        </td>
        <td class="{{ 'green' if t.pnl >= 0 else 'red' }}">
          {{ '+' if t.pnl >= 0 else '' }}{{ t.pnl }} $
        </td>
      </tr>
      {% endfor %}
    </table>
  </div>
</div>
{% endif %}

<!-- LOGS -->
<div class="section">
  <div class="section-title">📡 Logs en direct</div>
  <div class="section-body">
    <div class="log-box">
      {% for line in logs %}
        <div class="
          {{ 'log-alert'  if 'ERROR' in line or 'LOSS' in line else
             'log-signal' if 'WIN' in line or 'SIGNAL' in line else
             'log-warn'   if 'WARNING' in line or 'ALERT' in line else '' }}
        ">{{ line.strip() }}</div>
      {% endfor %}
    </div>
  </div>
</div>

<div class="refresh-note">
  Page actualisée automatiquement toutes les 60 secondes
</div>

</body>
</html>
"""

@app.route("/")
def dashboard():
    journal = load_journal()
    stats   = get_stats(journal)
    logs    = load_logs(30)
    now     = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    return render_template_string(
        HTML,
        stats=stats,
        trades=journal,
        logs=logs,
        now=now
    )

@app.route("/api/stats")
def api_stats():
    journal = load_journal()
    return jsonify(get_stats(journal))

@app.route("/api/trades")
def api_trades():
    return jsonify(load_journal())

@app.route("/api/logs")
def api_logs():
    logs = load_logs(50)
    return jsonify({"logs": [l.strip() for l in logs]})

if __name__ == "__main__":
    app.run(debug=False)
