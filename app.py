"""Crypto Monitor — backend Flask.

Sirve la SPA (index.html) y expone endpoints propios, por activo (BTC, ETH,
BNB), para precio de Binance, flujo ETF (scrapeado de Farside, cuando el
activo tiene ETF spot) y el análisis de sesgo alcista/bajista. Todo pasa por
este backend para evitar problemas de CORS/geo-bloqueo en el navegador y para
poder cachear el scrape de Farside.
"""

import os

from flask import Flask, abort, jsonify, send_from_directory

import binance_client
import etf_flows
from analysis import analizar_estado
from assets_config import ASSETS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, static_folder=None)


def _asset_config(asset):
    cfg = ASSETS.get(asset)
    if cfg is None:
        abort(404, description=f"Activo desconocido: '{asset}'. Válidos: {list(ASSETS)}")
    return cfg


@app.get("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/api/assets")
def api_assets():
    return jsonify({
        asset: {"label": cfg["label"], "tiene_etf": cfg["farside_slug"] is not None}
        for asset, cfg in ASSETS.items()
    })


@app.get("/api/<asset>/price")
def api_price(asset):
    cfg = _asset_config(asset)
    try:
        return jsonify(binance_client.get_ticker(cfg["symbol"]))
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.get("/api/<asset>/etf-flows")
def api_etf_flows(asset):
    cfg = _asset_config(asset)
    if cfg["farside_slug"] is None:
        return jsonify({"flows": [], "soportado": False})
    try:
        flows = etf_flows.get_etf_flows(cfg["farside_slug"])
        return jsonify({"flows": flows[-14:], "soportado": True})  # ~2 semanas alcanza para el gráfico
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.get("/api/<asset>/analysis")
def api_analysis(asset):
    cfg = _asset_config(asset)

    try:
        ticker = binance_client.get_ticker(cfg["symbol"])
    except Exception as e:
        return jsonify({"error": f"No se pudo leer Binance: {e}"}), 502

    funding = binance_client.get_funding_rate(cfg["symbol"])

    flujo_7d, recientes = None, []
    if cfg["farside_slug"] is not None:
        try:
            flujo_7d, recientes = etf_flows.get_net_flow_usd(cfg["farside_slug"], days=7)
        except Exception:
            pass

    estado = analizar_estado(ticker, flujo_7d, funding)

    return jsonify({
        "asset": asset,
        "label": cfg["label"],
        "ticker": ticker,
        "funding_rate_pct": funding,
        "etf_soportado": cfg["farside_slug"] is not None,
        "etf_flujo_7d_dias_con_dato": [r["fecha"] for r in recientes],
        "analisis": estado,
        "nota_etf": "Los flujos de ETF son T+1 (Farside los publica con el cierre del día anterior en EE.UU.)",
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
