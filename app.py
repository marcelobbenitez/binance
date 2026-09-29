"""BTC Monitor — backend Flask.

Sirve la SPA (index.html) y expone endpoints propios para precio de Binance,
flujo ETF (scrapeado de Farside) y el análisis de sesgo alcista/bajista. Todo
pasa por este backend para evitar problemas de CORS/geo-bloqueo en el
navegador y para poder cachear el scrape de Farside.
"""

from flask import Flask, jsonify, send_from_directory

import binance_client
import etf_flows
from analysis import analizar_estado

app = Flask(__name__, static_folder=None)


@app.get("/")
def index():
    return send_from_directory(".", "index.html")


@app.get("/api/btc")
def api_btc():
    try:
        return jsonify(binance_client.get_btc_ticker())
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.get("/api/etf-flows")
def api_etf_flows():
    try:
        flows = etf_flows.get_etf_flows()
        return jsonify({"flows": flows[-14:]})  # últimas ~2 semanas alcanza para el gráfico
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.get("/api/analysis")
def api_analysis():
    try:
        btc = binance_client.get_btc_ticker()
    except Exception as e:
        return jsonify({"error": f"No se pudo leer Binance: {e}"}), 502

    funding = binance_client.get_funding_rate()

    try:
        flujo_7d, recientes = etf_flows.get_net_flow_usd(days=7)
    except Exception:
        flujo_7d, recientes = None, []

    estado = analizar_estado(btc, flujo_7d, funding)

    return jsonify({
        "btc": btc,
        "funding_rate_pct": funding,
        "etf_flujo_7d_dias_con_dato": [r["fecha"] for r in recientes],
        "analisis": estado,
        "nota_etf": "Los flujos de ETF son T+1 (Farside los publica con el cierre del día anterior en EE.UU.)",
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
